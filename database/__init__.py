"""database - SQLite schema and init with error handling."""

def init_db():
    from .models import init_db as _f
    return _f()

try:
    from .models import (
        db, init_db,
        NewsItem, GeneratedScript, UsedMedia,
        PostLog, Analytics, AgentMemory, TaskQueue,
        DeadLetterTask,
    )
except ImportError as _e:
    import sys
    print(f"[ERROR] database models failed: {_e}", file=sys.stderr)
    print("  Fix: pip install peewee --break-system-packages", file=sys.stderr)
