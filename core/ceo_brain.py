"""
core/ceo_brain.py
==================
CEO Brain - Asynchronous Master Controller

Design philosophy:
  - Event-driven: master_wakeup_cycle() runs every 30-60s, NOT a busy loop.
    It sleeps between cycles using asyncio.sleep() - zero CPU while idle.
  - One agent at a time: wakes agents sequentially to avoid RAM spikes.
  - Resource-aware: checks psutil before each agent wakeup.
  - Uses chain-of-responsibility pipeline (core/pipeline.py).
  - Dual LLM: Ollama primary (local, private), Grok API fallback.
  - Tool calls: LLM outputs <tool>{...}</tool> blocks for agent management.
"""

from __future__ import annotations
import asyncio
import json
import re
import time
import requests

from config.settings import OLLAMA_HOST, OLLAMA_MODEL
from utils.logger import get_logger

logger = get_logger("core.ceo_brain")

# Wakeup interval in seconds (adjustable via CLI)
WAKEUP_INTERVAL = 45

CEO_SYSTEM = """You are the CEO Brain of Spidergram - an autonomous multi-agent Instagram news engine.

Capabilities:
1. Manage agents (create/edit/delete/run)
2. Analyse performance data and adjust strategy
3. Modify Python modules (with backup)
4. Manage API keys securely
5. Respond to user commands

Tool call format: <tool>{"name": "tool_name", "args": {...}}</tool>

Available tools:
- list_agents: {}
- create_agent: {"name": str, "niche": str, "prompt": str, "keywords": list}
- edit_agent: {"agent_id": str, "updates": dict}
- delete_agent: {"agent_id": str}
- set_credentials: {"agent_id": str, "ig_user_id": str, "access_token": str}
- set_api_key: {"name": str, "value": str}
- list_api_keys: {}
- read_module: {"path": str}
- modify_module: {"path": str, "instruction": str}
- rollback_module: {"path": str}
- run_agent: {"agent_id": str, "dry_run": bool}
- performance_report: {}
- system_health: {}
- dead_letter_report: {}

Think step-by-step. Be decisive and technically precise.
"""


# ── LLM helpers ─────────────────────────────────────────────────────────────

def _ollama_chat(messages):
    """Call local Ollama. Uses smallest available model for 8GB RAM."""
    # Prefer small models: llama3.2:3b, phi3:mini, gemma3
    model = OLLAMA_MODEL  # set in config/settings.py
    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model":   model,
                "messages": messages,
                "stream":  False,
                "options": {"temperature": 0.7, "num_ctx": 2048},
            },
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["message"]["content"].strip()
    except Exception as exc:
        logger.warning(f"Ollama failed ({model}): {exc}")
        return ""


def _grok_chat(messages):
    """Grok API fallback when Ollama unavailable."""
    from integrations.grok import chat as grok
    return grok(messages)


def _llm(messages):
    result = _ollama_chat(messages)
    if not result:
        logger.info("Falling back to Grok API...")
        result = _grok_chat(messages)
    return result or "Both AI backends unavailable."


def _extract_tool_call(text):
    match = re.search(r"<tool>(.*?)</tool>", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            return data.get("name"), data.get("args", {})
        except json.JSONDecodeError:
            pass
    return None, None


# ── Tool executor ────────────────────────────────────────────────────────────

def _execute_tool(name, args):
    try:
        if name == "list_agents":
            from agents import list_agents
            return json.dumps(list_agents(), indent=2)

        elif name == "create_agent":
            from agents import create_agent
            a = create_agent(args["name"], args["niche"],
                             args["prompt"], args.get("keywords", []))
            return f"Agent created: {a.id}"

        elif name == "edit_agent":
            from agents import edit_agent
            ok = edit_agent(args["agent_id"], args["updates"])
            return "Updated." if ok else "Agent not found."

        elif name == "delete_agent":
            from agents import delete_agent
            ok = delete_agent(args["agent_id"])
            return "Deleted." if ok else "Not found."

        elif name == "set_credentials":
            from agents import set_agent_credentials
            ok = set_agent_credentials(args["agent_id"],
                                       args["ig_user_id"], args["access_token"])
            return "Credentials set." if ok else "Agent not found."

        elif name == "set_api_key":
            from utils import set_key
            set_key(args["name"], args["value"])
            return f"Key stored: {args['name']}"

        elif name == "list_api_keys":
            from utils import list_keys
            return str(list_keys())

        elif name == "read_module":
            from self_modify import read_module
            return read_module(args["path"])

        elif name == "list_modules":
            from self_modify import get_module_summary
            return get_module_summary()

        elif name == "modify_module":
            return _modify_module_flow(args["path"], args["instruction"])

        elif name == "rollback_module":
            from self_modify import rollback
            ok, msg = rollback(args["path"])
            return msg

        elif name == "run_agent":
            from agents import get_agent
            agent = get_agent(args["agent_id"])
            if not agent:
                return "Agent not found."
            # Fire-and-forget in background task
            asyncio.ensure_future(
                _run_agent_pipeline(agent, args.get("dry_run", False))
            )
            return f"Pipeline queued for {agent.name}"

        elif name == "performance_report":
            return _build_perf_report()

        elif name == "system_health":
            return _build_health_report()

        elif name == "dead_letter_report":
            return _build_dead_letter_report()

        else:
            return f"Unknown tool: {name}"
    except Exception as exc:
        return f"Tool error: {exc}"


async def _run_agent_pipeline(agent, dry_run=False):
    """Async pipeline runner for a single agent using chain-of-responsibility."""
    from core.resource_manager import check_resources
    from core.pipeline import build_pipeline

    ok, reason = check_resources("heavy")
    if not ok:
        logger.warning(f"Skipping {agent.name}: {reason}")
        return

    ctx = {
        "agent_config": agent.config,
        "dry_run":      dry_run,
        "light_mode":   dry_run,   # dry-run uses light mode
        "errors":       [],
    }
    head = build_pipeline(dry_run=dry_run)
    await head.wakeup(ctx)


def _modify_module_flow(path, instruction):
    try:
        from self_modify import read_module, apply_modification
        current = read_module(path)
    except FileNotFoundError as exc:
        return str(exc)
    messages = [
        {"role": "system", "content":
         "You are an expert Python engineer. Return ONLY the complete modified "
         "Python file with no markdown fences."},
        {"role": "user", "content":
         f"Module: {path}\n\nInstruction: {instruction}\n\nCurrent code:\n{current}"},
    ]
    new_code = _llm(messages)
    ok, msg  = apply_modification(path, new_code)
    return msg


def _build_perf_report():
    from database.models import PostLog, db
    with db:
        total   = PostLog.select().count()
        success = PostLog.select().where(PostLog.status == "success").count()
        failed  = PostLog.select().where(PostLog.status == "failed").count()
    return (
        f"Performance Report:\n"
        f"  Total:    {total}\n"
        f"  Success:  {success}\n"
        f"  Failed:   {failed}\n"
        f"  Rate:     {round(success/max(total,1)*100,1)}%"
    )


def _build_health_report():
    from core.resource_manager import get_system_stats
    free, cpu = get_system_stats()
    gb = free / 1024**3
    return (
        f"System Health:\n"
        f"  Free RAM: {gb:.1f} GB\n"
        f"  CPU:      {cpu:.1f}%"
    )


def _build_dead_letter_report():
    try:
        from database.models import DeadLetterTask, db
        with db:
            tasks = list(DeadLetterTask.select()
                         .where(DeadLetterTask.resolved == False)
                         .order_by(DeadLetterTask.created_at.desc())
                         .limit(10).dicts())
        if not tasks:
            return "No pending dead-letter tasks."
        lines = [f"Dead-Letter Queue ({len(tasks)} unresolved):"]
        for t in tasks:
            lines.append(f"  [{t['step_name']}] {t['agent_id']}: {t['reason'][:80]}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Dead-letter report error: {exc}"


# ── Main CEO Brain class ──────────────────────────────────────────────────────

class CEOBrain:
    """
    Async CEO Brain controller.
    master_wakeup_cycle() runs periodically (event-driven, not busy-poll).
    """

    def __init__(self, wakeup_interval=WAKEUP_INTERVAL):
        self.wakeup_interval = wakeup_interval
        self.conversation    = [{"role": "system", "content": CEO_SYSTEM}]
        self._running        = False
        self._paused_agents  = set()   # agents user has manually stopped
        from agents import load_all_agents
        load_all_agents()
        logger.info(f"CEO Brain initialised (wakeup every {wakeup_interval}s).")

    # ── Async wakeup cycle ───────────────────────────────────────────────────

    async def master_wakeup_cycle(self) -> None:
        """
        Event-driven master loop.
        Wakes ONE agent per cycle. Checks resources before each wakeup.
        Sleeps wakeup_interval seconds between cycles using asyncio.sleep()
        - this yields control to the event loop (zero CPU while sleeping).
        """
        self._running = True
        logger.info("CEO Brain master_wakeup_cycle started.")

        while self._running:
            try:
                await self._tick()
            except Exception as exc:
                logger.exception(f"CEO Brain cycle error: {exc}")

            # Non-blocking sleep - yields to event loop
            await asyncio.sleep(self.wakeup_interval)

        logger.info("CEO Brain master_wakeup_cycle stopped.")

    async def _tick(self) -> None:
        """One wakeup cycle: check resources, pick agent, fire pipeline."""
        from core.resource_manager import check_resources, get_system_stats
        from agents import load_all_agents

        free, cpu = get_system_stats()
        logger.info(f"CEO wakeup: RAM={free/1024**3:.1f}GB CPU={cpu:.1f}%")

        ok, reason = check_resources("heavy")
        if not ok:
            logger.warning(f"CEO skipping this cycle: {reason}")
            return

        agents = load_all_agents()
        for agent_id, agent in agents.items():
            if agent_id in self._paused_agents:
                continue
            if not agent.config.get("active", True):
                continue
            logger.info(f"CEO waking agent: {agent.name}")
            await _run_agent_pipeline(agent, dry_run=False)
            break   # one agent per cycle - prevents RAM spikes

    def stop(self) -> None:
        self._running = False

    def pause_agent(self, agent_id: str) -> None:
        self._paused_agents.add(agent_id)
        logger.info(f"Agent paused: {agent_id}")

    def resume_agent(self, agent_id: str) -> None:
        self._paused_agents.discard(agent_id)
        logger.info(f"Agent resumed: {agent_id}")

    # ── Synchronous chat (for Flask/terminal) ────────────────────────────────

    def chat(self, user_message: str) -> str:
        """
        Synchronous chat entry point (used by Flask /chat route and terminal).
        Processes message, optionally executes tool calls, returns final reply.
        """
        self.conversation.append({"role": "user", "content": user_message})
        raw_reply = _llm(self.conversation)

        tool_name, tool_args = _extract_tool_call(raw_reply)
        if tool_name:
            logger.info(f"CEO tool: {tool_name}({tool_args})")
            tool_result = _execute_tool(tool_name, tool_args or {})
            self.conversation.append({"role": "assistant", "content": raw_reply})
            self.conversation.append({"role": "user",
                                       "content": f"Tool result: {tool_result}"})
            final_reply = _llm(self.conversation)
        else:
            final_reply = raw_reply

        # Keep conversation trimmed (last 20 messages + system)
        if len(self.conversation) > 22:
            self.conversation = [self.conversation[0]] + self.conversation[-20:]

        self.conversation.append({"role": "assistant", "content": final_reply})
        return final_reply

    def quick_command(self, command: str, args: dict = None) -> str:
        return _execute_tool(command, args or {})
