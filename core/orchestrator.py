"""
core/orchestrator.py
=====================
Async orchestrator - drives the CEO Brain wakeup cycle.
Uses asyncio event loop with proper resource management.
No busy polling - asyncio.sleep() yields CPU between cycles.
"""

import asyncio
import json
import threading
import time

import schedule

from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from database.models import PostLog, TaskQueue, db
from agents import load_all_agents
from utils.logger import get_logger

logger = get_logger("core.orchestrator")


# ── Helper: telegram (non-blocking) ─────────────────────────────────────────

def _tg_send(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    import requests
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text[:4096]},
            timeout=8,
        )
    except Exception as exc:
        logger.debug(f"Telegram send failed: {exc}")


def _tg_get_updates():
    if not TELEGRAM_BOT_TOKEN:
        return []
    import requests
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
            params={"timeout": 1, "offset": -1},
            timeout=5,
        )
        return r.json().get("result", [])
    except Exception:
        return []


# ── Dead-letter queue helpers ────────────────────────────────────────────────

def flush_task_queue(max_tasks: int = 20) -> None:
    """Process pending tasks from the DB task queue."""
    agents = load_all_agents()
    with db:
        pending = (TaskQueue
                   .select()
                   .where(TaskQueue.status == "pending")
                   .order_by(TaskQueue.priority.desc(), TaskQueue.created_at)
                   .limit(max_tasks))
        for task in pending:
            agent = agents.get(task.agent_id)
            if not agent:
                task.status = "failed"
                task.error  = "Agent not found"
                task.save()
                continue
            try:
                task.status = "running"
                task.save()
                args = json.loads(task.payload) if task.payload else {}
                agent.enqueue(task.task_type, args, priority=task.priority)
                task.status = "done"
            except Exception as exc:
                task.status = "failed"
                task.error  = str(exc)[:500]
                logger.error(f"Task {task.id} failed: {exc}")
            finally:
                task.save()


# ── Sync runner (used for --dry-run / --once) ────────────────────────────────

def run_once(dry_run: bool = False) -> None:
    """
    Run pipeline once for all active agents synchronously.
    Used by: python main.py  (no flags) and --dry-run.
    """
    from database import init_db
    init_db()
    agents = load_all_agents()
    logger.info(f"run_once: {len(agents)} agents (dry_run={dry_run})")
    flush_task_queue()

    from core.resource_manager import check_resources
    ok, reason = check_resources("heavy")
    if not ok:
        logger.warning(f"Resource check failed: {reason} - delaying 60s")
        time.sleep(60)
        return

    # Run async pipeline for each agent sequentially
    async def _run_all():
        from core.ceo_brain import _run_agent_pipeline
        for agent_id, agent in agents.items():
            if not agent.config.get("active", True):
                continue
            logger.info(f"Running agent: {agent.name}")
            await _run_agent_pipeline(agent, dry_run=dry_run)

    asyncio.run(_run_all())
    logger.info("run_once complete.")


# ── Async loop (used for --scheduled / --both) ───────────────────────────────

def run_loop(dry_run: bool = False) -> None:
    """
    Start the async CEO Brain wakeup cycle.
    Blocking - call from a thread (used by --both flag).
    """
    from database import init_db
    init_db()
    load_all_agents()
    logger.info(f"run_loop starting (dry_run={dry_run})")
    asyncio.run(_async_loop(dry_run=dry_run))


async def _async_loop(dry_run: bool = False) -> None:
    """
    Async entry point: starts CEO Brain wakeup cycle + optional telegram loop.
    Both run concurrently in the same event loop.
    """
    from core.ceo_brain import CEOBrain
    brain = CEOBrain()

    tasks = [asyncio.create_task(brain.master_wakeup_cycle())]

    if TELEGRAM_BOT_TOKEN:
        tasks.append(asyncio.create_task(_telegram_loop(brain)))

    await asyncio.gather(*tasks)


async def _telegram_loop(brain) -> None:
    """Process Telegram commands every 30s in async fashion."""
    loop = asyncio.get_event_loop()
    while True:
        try:
            updates = await loop.run_in_executor(None, _tg_get_updates)
            for upd in updates:
                msg = upd.get("message", {}).get("text", "").strip()
                if msg:
                    reply = brain.chat(msg)
                    await loop.run_in_executor(None, _tg_send, reply)
        except Exception as exc:
            logger.debug(f"Telegram loop error: {exc}")
        await asyncio.sleep(30)


# ── Schedule helpers ─────────────────────────────────────────────────────────

def setup_schedule(posting_times=None, dry_run: bool = False) -> None:
    times = posting_times or ["09:00", "13:00", "18:00", "21:00"]
    for t in times:
        schedule.every().day.at(t).do(run_once, dry_run=dry_run)
        logger.info(f"Scheduled run at {t}")


def generate_report() -> None:
    """Generate and log nightly performance summary."""
    from datetime import date, datetime
    from database.models import PostLog, db
    with db:
        today = datetime.combine(date.today(), datetime.min.time())
        total   = PostLog.select().where(PostLog.posted_at >= today).count()
        success = PostLog.select().where(
            PostLog.posted_at >= today, PostLog.status == "success").count()
        failed  = PostLog.select().where(
            PostLog.posted_at >= today, PostLog.status == "failed").count()
    msg = (f"Daily Report: {total} posts | "
           f"{success} success | {failed} failed | "
           f"rate={round(success/max(total,1)*100,1)}%")
    logger.info(msg)
    _tg_send(msg)
