"""
core/resource_manager.py
=========================
Global semaphore pool for resource-limited execution on 8 GB machines.

Design philosophy:
  - Only ONE heavy pipeline (video render / model inference) runs at a time.
  - Up to TWO light tasks (news fetch, dedup, script gen) may run concurrently.
  - Before any heavy work, the caller acquires heavy_sem; this blocks if another
    heavy task is already running, preventing OOM crashes.
  - psutil is used to verify available RAM before waking any agent.

Usage:
    async with heavy_sem:
        await render_video(...)

    async with light_sem:
        await fetch_news(...)
"""

import asyncio
import threading

# ── Semaphore definitions ────────────────────────────────────────────────────
# Only 1 heavy task (video/model) at a time on 8 GB RAM
heavy_sem = asyncio.Semaphore(1)

# Up to 2 light tasks (fetch/dedup/script) concurrently
light_sem  = asyncio.Semaphore(2)

# Memory thresholds (bytes)
MIN_FREE_RAM_HEAVY = 2.0 * 1024 ** 3   # need >= 2 GB free before heavy task
MIN_FREE_RAM_LIGHT = 0.5 * 1024 ** 3   # need >= 500 MB free before light task
MAX_CPU_PCT        = 85.0               # do not start if CPU > 85%


def get_system_stats():
    """Return (free_ram_bytes, cpu_pct). Safe even if psutil missing."""
    try:
        import psutil
        mem = psutil.virtual_memory()
        return mem.available, psutil.cpu_percent(interval=0.1)
    except ImportError:
        return float("inf"), 0.0


def check_resources(mode="light"):
    """
    Return (ok: bool, reason: str).
    Checks RAM and CPU before allowing a task to start.
    """
    free_ram, cpu = get_system_stats()
    min_ram = MIN_FREE_RAM_HEAVY if mode == "heavy" else MIN_FREE_RAM_LIGHT
    if free_ram < min_ram:
        gb = free_ram / 1024 ** 3
        return False, f"Low RAM: {gb:.1f} GB free (need {min_ram/1024**3:.1f} GB for {mode})"
    if cpu > MAX_CPU_PCT:
        return False, f"High CPU: {cpu:.1f}% (limit {MAX_CPU_PCT}%)"
    return True, "ok"


class ResourceGuard:
    """
    Async context manager that acquires the right semaphore AND
    checks system resources before proceeding.

    Example:
        async with ResourceGuard("heavy"):
            await do_heavy_work()
    """
    def __init__(self, mode="light"):
        self.mode = mode
        self._sem = heavy_sem if mode == "heavy" else light_sem

    async def __aenter__(self):
        ok, reason = check_resources(self.mode)
        if not ok:
            raise RuntimeError(f"Resource check failed: {reason}")
        await self._sem.acquire()
        return self

    async def __aexit__(self, *_):
        self._sem.release()
