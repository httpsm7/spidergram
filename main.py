"""
main.py  -  Spidergram v3 Entry Point
======================================
Usage:
  python main.py                      Run pipeline once (all active agents)
  python main.py --scheduled          Start async scheduler (blocking)
  python main.py --dashboard          Start Flask dashboard only
  python main.py --both               Async scheduler + dashboard (recommended)
  python main.py --chat               Interactive CEO Brain terminal chat
  python main.py --dry-run            Full pipeline, no actual IG posting
  python main.py --agent <id>         Run one specific agent
  python main.py --light              Low-resource mode (480p, small models)
  python main.py --ultra-light        Minimum resources (480p, 15fps, text only)
  python main.py --install-models     Register Modelfiles with Ollama
  python main.py --report             Generate nightly report
  python main.py --dead-letters       Show dead-letter queue

Fix log (--both bug):
  root cause was run_loop() not accepting dry_run param, now fixed.
  Also fixed threading.Thread call to not pass positional args when not needed.
"""

import argparse
import sys
import threading
from pathlib import Path

# ── Bootstrap sys.path (MUST be before any project imports) ─────────────────
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# ── Verify critical packages ─────────────────────────────────────────────────
def _check_deps():
    missing = []
    required = {
        "flask":       "flask",
        "peewee":      "peewee",
        "cryptography":"cryptography",
        "dotenv":      "python-dotenv",
        "requests":    "requests",
        "schedule":    "schedule",
        "psutil":      "psutil",
    }
    for import_name, pip_name in required.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pip_name)
    if missing:
        print(f"[ERROR] Missing packages: {', '.join(missing)}")
        print(f"  Fix: pip install {' '.join(missing)} --break-system-packages")
        sys.exit(1)

_check_deps()

from database import init_db
from agents import load_all_agents, get_agent
from utils.logger import get_logger

logger = get_logger("main")

# ── Global light-mode flag (set by CLI args) ─────────────────────────────────
LIGHT_MODE       = False
ULTRA_LIGHT_MODE = False


def _bootstrap():
    init_db()
    load_all_agents()


def run_once(dry_run: bool = False):
    _bootstrap()
    from core.orchestrator import run_once as _once
    _once(dry_run=dry_run)


def run_scheduled(dry_run: bool = False):
    _bootstrap()
    from core.orchestrator import run_loop
    run_loop(dry_run=dry_run)


def run_dashboard():
    _bootstrap()
    try:
        from ui.web_dashboard.app import start_dashboard
        start_dashboard()
    except ImportError as e:
        logger.error(f"Dashboard import failed: {e}")
        sys.exit(1)


def run_both(dry_run: bool = False):
    """
    Fix: previous version passed dry_run as positional arg to Thread target.
    Now uses kwargs dict to avoid argument mismatch.
    run_loop() correctly accepts dry_run=False since our orchestrator fix.
    """
    _bootstrap()
    try:
        from core.orchestrator import run_loop
        from ui.web_dashboard.app import start_dashboard
    except ImportError as e:
        logger.error(f"Import failed: {e}")
        sys.exit(1)

    # BUG FIX: use kwargs instead of positional args
    t = threading.Thread(
        target=run_loop,
        kwargs={"dry_run": dry_run},
        daemon=True,
        name="spidergram-scheduler",
    )
    t.start()
    logger.info("Async scheduler started in background thread.")
    start_dashboard()   # blocking - runs Flask in foreground


def run_chat():
    _bootstrap()
    try:
        from ui.chat_interface.chat import run_chat as _chat
        _chat()
    except ImportError as e:
        logger.error(f"Chat import failed: {e}")


def install_models():
    mf_dir = BASE_DIR / "modelfiles"
    if not mf_dir.exists():
        logger.error("modelfiles/ directory not found.")
        return
    import subprocess
    for mf in mf_dir.glob("Modelfile.*"):
        name   = mf.stem.replace("Modelfile.", "").lower()
        logger.info(f"Installing model: {name}")
        result = subprocess.run(
            ["ollama", "create", name, "-f", str(mf)],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            logger.info(f"  OK: {name}")
        else:
            logger.warning(f"  Failed: {name} - {result.stderr[:80]}")


def run_report():
    _bootstrap()
    from core.orchestrator import generate_report
    generate_report()


def show_dead_letters():
    _bootstrap()
    try:
        from database.models import DeadLetterTask, db
        with db:
            tasks = list(DeadLetterTask.select()
                         .where(DeadLetterTask.resolved == False)
                         .order_by(DeadLetterTask.created_at.desc())
                         .limit(20).dicts())
        if not tasks:
            print("No pending dead-letter tasks.")
            return
        print(f"Dead-Letter Queue ({len(tasks)} unresolved):")
        for t in tasks:
            print(f"  [{t['created_at']}] [{t['step_name']}] {t['agent_id']}: {t['reason'][:80]}")
    except Exception as e:
        print(f"Error: {e}")


def main():
    global LIGHT_MODE, ULTRA_LIGHT_MODE

    parser = argparse.ArgumentParser(
        description="Spidergram v3 - Autonomous AI Instagram Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--scheduled",      action="store_true")
    parser.add_argument("--dashboard",      action="store_true")
    parser.add_argument("--both",           action="store_true")
    parser.add_argument("--chat",           action="store_true")
    parser.add_argument("--dry-run",        action="store_true")
    parser.add_argument("--agent",          type=str)
    parser.add_argument("--light",          action="store_true",
                        help="Low resource: 480p video, small LLM models")
    parser.add_argument("--ultra-light",    action="store_true",
                        help="Minimum resources: 480p, 15fps, pyttsx3 TTS only")
    parser.add_argument("--install-models", action="store_true")
    parser.add_argument("--report",         action="store_true")
    parser.add_argument("--dead-letters",   action="store_true")
    args = parser.parse_args()

    LIGHT_MODE       = args.light or args.ultra_light
    ULTRA_LIGHT_MODE = args.ultra_light

    if ULTRA_LIGHT_MODE:
        logger.info("Ultra-light mode: minimal resources, pyttsx3 TTS, 480p/15fps video")
        # Override settings for ultra-light mode
        import config.settings as cfg
        cfg.VIDEO_FPS    = 15
        cfg.VIDEO_W      = 480
        cfg.VIDEO_H      = 854
        cfg.OLLAMA_MODEL = "phi3:mini"

    elif LIGHT_MODE:
        logger.info("Light mode: 480p video, llama3.2:3b model")
        import config.settings as cfg
        cfg.OLLAMA_MODEL = "llama3.2:3b"

    logger.info(f"Spidergram v3 starting | cwd={BASE_DIR}")

    if args.install_models:
        install_models()
    elif args.scheduled:
        run_scheduled(dry_run=args.dry_run)
    elif args.dashboard:
        run_dashboard()
    elif args.both:
        run_both(dry_run=args.dry_run)
    elif args.chat:
        run_chat()
    elif args.report:
        run_report()
    elif args.dead_letters:
        show_dead_letters()
    elif args.agent:
        _bootstrap()
        agent = get_agent(args.agent)
        if not agent:
            logger.error(f"Agent '{args.agent}' not found.")
            sys.exit(1)
        import asyncio
        from core.ceo_brain import _run_agent_pipeline
        asyncio.run(_run_agent_pipeline(agent, dry_run=args.dry_run))
    else:
        run_once(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
