"""ImageStep - Step 4: Fetch media images from Pexels."""
import asyncio
from core.pipeline import PipelineStep, StepResult
from core.resource_manager import ResourceGuard


class ImageStep(PipelineStep):
    name = "image_fetcher"

    async def process(self, ctx):
        agent_cfg = ctx.get("agent_config", {})
        keywords  = agent_cfg.get("news_keywords", ["news"])
        async with ResourceGuard("light"):
            loop = asyncio.get_event_loop()
            images  = await loop.run_in_executor(None, _fetch_imgs, keywords)
            bg_vid  = ""
            if not images:
                bg_vid = await loop.run_in_executor(None, _fetch_bg, keywords)
        ctx["image_paths"] = images
        ctx["bg_video"]    = bg_vid
        return StepResult.ok(f"{len(images)} images, bg_video={'yes' if bg_vid else 'no'}")


def _fetch_imgs(keywords):
    from pipeline.media_fetcher import fetch_images
    return fetch_images(keywords, count=4)

def _fetch_bg(keywords):
    from pipeline.media_fetcher import fetch_background_video
    return fetch_background_video(keywords)
