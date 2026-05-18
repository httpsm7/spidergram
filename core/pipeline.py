"""
core/pipeline.py
=================
Chain-of-Responsibility pipeline framework.

Design:
  Each processing step subclasses PipelineStep and implements async process(ctx).
  When process() succeeds, the step automatically wakes the next step via
  await next_step.wakeup(ctx).
  No central polling loop is needed; each step fires the next upon completion.

Context object (dict) flows through the chain and accumulates results:
  ctx["agent_config"]   - agent configuration dict
  ctx["news_item"]      - NewsItem DB record
  ctx["script"]         - GeneratedScript record
  ctx["image_paths"]    - list of local image paths
  ctx["audio_path"]     - local audio file path
  ctx["video_path"]     - local video file path
  ctx["dry_run"]        - bool - skip irreversible actions
  ctx["errors"]         - list of error strings (dead-letter log)
  ctx["log"]            - PostLog record (set by publisher)
"""

from __future__ import annotations
import asyncio
import time
from typing import Optional
from utils.logger import get_logger

logger = get_logger("core.pipeline")


class StepResult:
    """Result returned by each pipeline step."""
    __slots__ = ("success", "message", "data")

    def __init__(self, success: bool, message: str = "", data=None):
        self.success = success
        self.message = message
        self.data    = data

    @classmethod
    def ok(cls, message="", data=None):
        return cls(True, message, data)

    @classmethod
    def fail(cls, message=""):
        return cls(False, message)


class PipelineStep:
    """
    Abstract base for all pipeline steps.

    Subclasses must implement:
        async def process(self, ctx: dict) -> StepResult

    Chain wiring (done in orchestrator/ceo_brain):
        step_a.next_step = step_b
        step_b.next_step = step_c
        ...
    """
    name: str = "base_step"

    def __init__(self):
        self.next_step: Optional[PipelineStep] = None

    async def wakeup(self, ctx: dict) -> None:
        """
        Entry point called by the previous step (or the orchestrator).
        Runs process(), then triggers next_step if successful.
        Captures errors into ctx["errors"] instead of raising.
        """
        agent_id = ctx.get("agent_config", {}).get("id", "?")
        logger.info(f"[{agent_id}] Step [{self.name}] starting…")
        t0 = time.monotonic()

        try:
            result = await self.process(ctx)
        except Exception as exc:
            result = StepResult.fail(f"{self.name} exception: {exc}")
            logger.exception(f"[{agent_id}] Step [{self.name}] crashed: {exc}")

        elapsed = time.monotonic() - t0
        if result.success:
            logger.info(f"[{agent_id}] Step [{self.name}] done in {elapsed:.1f}s")
            # Propagate through chain
            if self.next_step:
                await self.next_step.wakeup(ctx)
        else:
            # Dead-letter: record failure
            ctx.setdefault("errors", []).append({
                "step":    self.name,
                "reason":  result.message,
                "elapsed": round(elapsed, 2),
            })
            logger.error(f"[{agent_id}] Step [{self.name}] FAILED: {result.message}")
            # Persist to dead-letter queue in DB
            _record_dead_letter(ctx, self.name, result.message)

    async def process(self, ctx: dict) -> StepResult:
        """Override in each concrete step."""
        raise NotImplementedError(f"{self.__class__.__name__}.process()")


def _record_dead_letter(ctx: dict, step_name: str, reason: str) -> None:
    """Persist a failed task to the DB dead-letter table."""
    try:
        from database.models import DeadLetterTask, db
        agent_id = ctx.get("agent_config", {}).get("id", "unknown")
        news_title = ""
        ni = ctx.get("news_item")
        if ni:
            news_title = getattr(ni, "title", "")
        with db:
            DeadLetterTask.create(
                agent_id   = agent_id,
                step_name  = step_name,
                news_title = news_title[:200],
                reason     = reason[:500],
            )
    except Exception as exc:
        logger.debug(f"Could not record dead-letter: {exc}")


def build_pipeline(dry_run: bool = False) -> PipelineStep:
    """
    Assemble the full pipeline chain and return the head step.
    Chain: NewsFetcher -> Dedup -> Script -> Image -> TTS -> Video -> Subtitle -> Publisher
    """
    from pipeline.steps.news_step      import NewsFetcherStep
    from pipeline.steps.dedup_step     import DeduplicatorStep
    from pipeline.steps.script_step    import ScriptStep
    from pipeline.steps.image_step     import ImageStep
    from pipeline.steps.tts_step       import TTSStep
    from pipeline.steps.video_step     import VideoStep
    from pipeline.steps.subtitle_step  import SubtitleStep
    from pipeline.steps.publish_step   import PublishStep

    fetch   = NewsFetcherStep()
    dedup   = DeduplicatorStep()
    script  = ScriptStep()
    image   = ImageStep()
    tts     = TTSStep()
    video   = VideoStep()
    sub     = SubtitleStep()
    pub     = PublishStep()

    # Wire the chain
    fetch.next_step  = dedup
    dedup.next_step  = script
    script.next_step = image
    image.next_step  = tts
    tts.next_step    = video
    video.next_step  = sub
    sub.next_step    = pub

    return fetch
