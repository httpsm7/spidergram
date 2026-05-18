"""PublishStep - Step 8: Upload to CDN and publish to Instagram."""
import asyncio
from core.pipeline import PipelineStep, StepResult


class PublishStep(PipelineStep):
    name = "publisher"

    async def process(self, ctx):
        video_path = ctx.get("video_path", "")
        script     = ctx.get("script")
        agent_cfg  = ctx.get("agent_config", {})
        news       = ctx.get("news_item")
        dry_run    = ctx.get("dry_run", False)

        if not video_path or not script:
            return StepResult.fail("Missing video or script for publish")

        if dry_run:
            import logging
            logging.getLogger("core.pipeline").info(
                f"[DRY RUN] Would publish: {getattr(news,'title','?')[:60]}")
            return StepResult.ok("Dry-run: skipped publish")

        loop = asyncio.get_event_loop()
        log  = await loop.run_in_executor(None, _pub,
            agent_cfg, video_path, script.caption,
            script.hashtags, getattr(news, "title", ""))

        ctx["log"] = log
        if log and log.status == "success":
            # Mark news as used
            await loop.run_in_executor(None, _mark_used, news)
            return StepResult.ok(f"Published! media_id={log.media_id}")
        return StepResult.fail(f"Publish failed: {getattr(log,'error','?')}")


def _pub(agent_cfg, video_path, caption, hashtags, news_title):
    from pipeline.publisher import publish
    return publish(agent_cfg, video_path, caption, hashtags, news_title)

def _mark_used(news):
    from database.models import db
    with db:
        news.used = True
        news.save()
