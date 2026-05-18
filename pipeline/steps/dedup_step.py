"""DeduplicatorStep - Step 2: Verify article is not a duplicate."""
import asyncio
from core.pipeline import PipelineStep, StepResult


class DeduplicatorStep(PipelineStep):
    name = "deduplicator"

    async def process(self, ctx):
        news = ctx.get("news_item")
        if not news:
            return StepResult.fail("No news item in context")
        loop = asyncio.get_event_loop()
        is_dup = await loop.run_in_executor(None, _check_dup, news.title)
        if is_dup:
            return StepResult.fail(f"Duplicate detected: {news.title[:60]}")
        return StepResult.ok("Article is unique")


def _check_dup(title):
    from pipeline.deduplicator import is_duplicate
    return is_duplicate(title)
