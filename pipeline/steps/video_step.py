"""
VideoStep - Step 6: Produce the final video reel.
Runs in a subprocess to isolate heavy memory use.
Uses ultrafast preset + low res for 8GB RAM machines.
"""
import asyncio
from core.pipeline import PipelineStep, StepResult
from core.resource_manager import ResourceGuard


class VideoStep(PipelineStep):
    name = "video_engine"

    async def process(self, ctx):
        script     = ctx.get("script")
        images     = ctx.get("image_paths", [])
        audio      = ctx.get("audio_path",  "")
        bg_video   = ctx.get("bg_video",    "")
        news       = ctx.get("news_item")
        light_mode = ctx.get("light_mode", False)

        if not script:
            return StepResult.fail("No script in context")

        # Heavy task - acquire heavy semaphore (only 1 video at a time)
        async with ResourceGuard("heavy"):
            loop = asyncio.get_event_loop()
            video_path = await loop.run_in_executor(None,
                _render, script, images, audio, bg_video,
                news.title if news else "", light_mode)

        if not video_path:
            return StepResult.fail("Video production returned empty path")
        ctx["video_path"] = video_path
        return StepResult.ok(f"Video: {video_path}")


def _render(script, images, audio, bg_video, headline, light_mode=False):
    from pipeline.video_engine import produce_video
    return produce_video(
        script=script, image_paths=images,
        audio_path=audio, bg_video=bg_video,
        headline=headline, light_mode=light_mode,
    )
