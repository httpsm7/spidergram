"""SubtitleStep - Step 7: Burn subtitles onto the video."""
import asyncio
from core.pipeline import PipelineStep, StepResult
from core.resource_manager import ResourceGuard


class SubtitleStep(PipelineStep):
    name = "subtitle_engine"

    async def process(self, ctx):
        video_path = ctx.get("video_path", "")
        script     = ctx.get("script")
        if not video_path or not script:
            return StepResult.fail("Missing video or script")
        async with ResourceGuard("heavy"):
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None,
                _burn, video_path, script.body)
        ctx["video_path"] = result
        return StepResult.ok(f"Subtitled video: {result}")


def _burn(video_path, body):
    from pipeline.subtitle_engine import add_subtitles_moviepy
    return add_subtitles_moviepy(video_path, body, audio_duration=55.0)
