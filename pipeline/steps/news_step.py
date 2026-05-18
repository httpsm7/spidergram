"""NewsFetcherStep - Step 1: Fetch news articles for the agent."""
import asyncio
from core.pipeline import PipelineStep, StepResult
from core.resource_manager import ResourceGuard


class NewsFetcherStep(PipelineStep):
    name = "news_fetcher"

    async def process(self, ctx):
        agent_cfg = ctx.get("agent_config", {})
        dry_run   = ctx.get("dry_run", False)
        async with ResourceGuard("light"):
            loop = asyncio.get_event_loop()
            # Run blocking DB/HTTP calls in thread pool
            new_items = await loop.run_in_executor(None,
                _fetch_sync, agent_cfg)
        if not new_items:
            return StepResult.fail("No new articles found")
        ctx["news_item"] = new_items[0]   # pass first unused item downstream
        ctx["all_items"] = new_items
        return StepResult.ok(f"Fetched {len(new_items)} articles")


def _fetch_sync(agent_cfg):
    from pipeline.news_fetcher import fetch_for_agent, get_unused_items
    fetch_for_agent(agent_cfg)
    cats = agent_cfg.get("news_categories", ["general"])
    return get_unused_items(agent_cfg["id"], cats[0], limit=1)
