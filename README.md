# Spidergram v3 — Autonomous AI Instagram News Engine

> Fully fixed, optimized, and rebuilt from the ground up.

## What's New in v3

| Feature | Description |
|---|---|
| **Async CEO Brain** | `master_wakeup_cycle()` — event-driven, zero CPU when idle |
| **Resource Manager** | Global semaphores (1 heavy / 2 light) — prevents OOM on 8 GB RAM |
| **Chain Pipeline** | 8-step chain-of-responsibility: each step triggers the next |
| **Dead-Letter Queue** | Failed tasks captured to DB, visible in dashboard |
| **Glassy UI Popups** | Click any stat card → frosted glass popup with live data |
| **SVG Icons** | All emojis replaced with proper SVG icons in pipeline UI |
| **API Monitor** | Per-API usage bars, 90% warning, reset times |
| **--light / --ultra-light** | Low-RAM modes: 480p, 15fps, phi3:mini model |
| **Agent API Management** | Add/remove API keys per agent from the dashboard |
| **Add Tokens** | Top up agent tokens from the Active Agents popup |

## Quick Start

```bash
# 1. Clone / extract
cd /home/user/spidergram

# 2. Install (one command)
python install.py

# 3. Add your API keys
nano .env

# 4. Run
python main.py --both              # scheduler + dashboard
python main.py --both --light      # 8 GB RAM machine
python main.py --both --ultra-light  # minimal resources
```

## Dashboard — http://localhost:7111

| Stat Card | Click Action |
|---|---|
| Posts Today | Popup: all posts made today |
| Total Success | Popup: successful posts list |
| Total Failed | Popup: failed posts + errors |
| Active Agents | Popup: agents with tokens + pause/resume |
| Queued/Quit | Popup: dead-letter queue |

## CLI Flags

```
python main.py                  Run pipeline once
python main.py --scheduled      Async scheduler loop
python main.py --dashboard      Flask dashboard only
python main.py --both           Both (recommended)
python main.py --dry-run        No real IG posting
python main.py --light          480p video, llama3.2:3b
python main.py --ultra-light    480p/15fps, phi3:mini
python main.py --agent <id>     Run single agent
python main.py --dead-letters   Show failed tasks
python main.py --report         Generate report
python main.py --install-models Register Ollama models
```

## For 8 GB RAM Machines

```bash
# Create swapfile (recommended)
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Run in light mode
python main.py --both --light
```

## API Keys Required

| Key | Service | Free Limit |
|---|---|---|
| `NEWSAPI_KEY` | NewsAPI | 100 req/day |
| `GNEWS_API_KEY` | GNews | 100 req/day |
| `PEXELS_API_KEY` | Pexels | 200 req/hr |
| `ELEVENLABS_API_KEY` | ElevenLabs TTS | 10K chars/mo |
| `GROK_API_KEY` | xAI Grok | 1M tokens/mo |
| `CLOUDINARY_URL` | Cloudinary CDN | 25 credits/mo |

## Architecture

```
main.py → orchestrator → CEOBrain.master_wakeup_cycle()
                              ↓ (every 45s, async sleep)
                         Resource check (psutil)
                              ↓
                         build_pipeline() → chain
                              ↓
    NewsFetcher → Dedup → Script → Image → TTS → Video → Subtitle → Publish
    (each step wakes next on success; failures → DeadLetterTask DB)
```

## Bugs Fixed in v3

1. `SyntaxError: invalid non-printable character U+00A0` — all `__init__.py` rewritten with pure ASCII
2. `ModuleNotFoundError: schedule` — lazy imports prevent cascade failures
3. `PermissionError: .env` — security module uses `data/encryption.key` fallback
4. `cannot import 'run_once' from orchestrator` — `run_once()` added
5. `run_loop()` doesn't accept `dry_run` — signature fixed
6. `--both` flag crash — uses `kwargs=` not positional `args=` in Thread
7. Python 3.9 `X | Y` union types — replaced with compatible syntax
8. `pexels.py` headers at module load with empty key — now lazy
9. `video_engine.py` double VideoFileClip open — fixed
10. `subtitle_engine.py` triple frame conversion — fixed to single correct conversion
11. `TaskQueue.args_json` → `TaskQueue.payload` — field name corrected
