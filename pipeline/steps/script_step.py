"""ScriptStep - Step 3: Generate narration script via Ollama/Grok."""
import asyncio
from core.pipeline import PipelineStep, StepResult
from core.resource_manager import ResourceGuard


class ScriptStep(PipelineStep):
    name = "script_engine"

    async def process(self, ctx):
        news       = ctx.get("news_item")
        agent_cfg  = ctx.get("agent_config", {})
        if not news:
            return StepResult.fail("No news item")
        async with ResourceGuard("light"):
            loop = asyncio.get_event_loop()
            script = await loop.run_in_executor(None,
                _gen_script, news, agent_cfg)
        if not script:
            return StepResult.fail("Script generation returned None")
        ctx["script"] = script
        return StepResult.ok(f"Script generated ({len(script.body)} chars)")


def _gen_script(news, agent_cfg):
    from pipeline.script_engine import generate_script
    return generate_script(news, agent_cfg)
