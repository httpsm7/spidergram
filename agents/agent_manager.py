"""
agents/agent_manager.py
────────────────────────
Create, edit, delete, and reload agents at runtime.
Used by both the CEO Brain and the chat/web interface.
"""

import json
from pathlib import Path
from agents.agent_template import BaseAgent
from config.settings import AGENTS_CONFIG
from utils import get_logger, load_json, save_json

logger = get_logger("agents.manager")

# Runtime registry: {agent_id → BaseAgent}
_registry: dict = {}


def load_all_agents() -> dict:
    """Load all agents from config/agents.json into the registry."""
    global _registry
    configs = load_json(AGENTS_CONFIG, default=[])
    _registry = {}
    for cfg in configs:
        if cfg.get("active", True):
            agent = BaseAgent(cfg)
            _registry[agent.id] = agent
            logger.debug(f"Loaded agent: {agent.id} ({agent.niche})")
    logger.info(f"Loaded {len(_registry)} agents.")
    return _registry


def get_agent(agent_id: str):
    return _registry.get(agent_id)


def list_agents():
    """Return summary dicts for all registered agents (includes all dashboard fields)."""
    from database.models import PostLog
    from datetime import date, datetime
    result = []
    for a in _registry.values():
        # Count today posts
        try:
            today_start = datetime.combine(date.today(), datetime.min.time())
            posts_today = PostLog.select().where(
                PostLog.agent_id == a.id,
                PostLog.posted_at >= today_start
            ).count()
        except Exception:
            posts_today = 0
        result.append({
            "id":           a.id,
            "name":         a.name,
            "niche":        a.niche,
            "active":       a.config.get("active", True),
            "posts_today":  posts_today,
            "ig_user_id":   a.config.get("ig_user_id", ""),
            "ig_access_token": a.config.get("access_token", ""),
            "post_times":   ",".join(a.config.get("posting_times", ["09:00","15:00","20:00"])),
            "prompt":       a.config.get("prompt", "")[:120],
            "tokens":       a.config.get("tokens", 1000),
            "color":        a.config.get("color", "#0a84ff"),
        })
    return result


def create_agent(name, niche, prompt, keywords=None, extra=None):
    """
    Dynamically create a new agent, persist to agents.json, and register it.
    """
    agent_id = name.lower().replace(" ", "_")
    cfg = {
        "id":             agent_id,
        "name":           name,
        "niche":          niche,
        "active":         True,
        "ig_user_id":     "",
        "access_token":   "",
        "news_keywords":  keywords or [niche],
        "news_categories":["general"],
        "language":       "en",
        "posting_times":  ["09:00", "15:00", "20:00"],
        "prompt":         prompt,
        "voice_style":    "professional",
        "memory":         {},
        **(extra or {}),
    }
    _persist_agent(cfg)
    agent = BaseAgent(cfg)
    _registry[agent_id] = agent
    logger.info(f"Agent created: {agent_id}")
    return agent


def edit_agent(agent_id: str, updates: dict) -> bool:
    """Update fields in an existing agent's config. Returns True on success."""
    configs = load_json(AGENTS_CONFIG, default=[])
    for i, cfg in enumerate(configs):
        if cfg["id"] == agent_id:
            configs[i].update(updates)
            save_json(AGENTS_CONFIG, configs)
            # Reload in registry
            agent = BaseAgent(configs[i])
            _registry[agent_id] = agent
            logger.info(f"Agent updated: {agent_id} | fields: {list(updates.keys())}")
            return True
    logger.warning(f"Agent not found for edit: {agent_id}")
    return False


def delete_agent(agent_id: str) -> bool:
    """Remove an agent from config and registry."""
    configs = load_json(AGENTS_CONFIG, default=[])
    before  = len(configs)
    configs = [c for c in configs if c["id"] != agent_id]
    if len(configs) == before:
        return False
    save_json(AGENTS_CONFIG, configs)
    _registry.pop(agent_id, None)
    logger.info(f"Agent deleted: {agent_id}")
    return True


def set_agent_credentials(agent_id: str, ig_user_id: str, access_token: str) -> bool:
    return edit_agent(agent_id, {"ig_user_id": ig_user_id, "access_token": access_token})


def _persist_agent(cfg: dict) -> None:
    configs = load_json(AGENTS_CONFIG, default=[])
    # Replace if exists, else append
    ids = [c["id"] for c in configs]
    if cfg["id"] in ids:
        configs[ids.index(cfg["id"])] = cfg
    else:
        configs.append(cfg)
    save_json(AGENTS_CONFIG, configs)
