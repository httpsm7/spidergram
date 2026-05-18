"""TTSStep - Step 5: Generate TTS audio via ElevenLabs or pyttsx3."""
import asyncio
from core.pipeline import PipelineStep, StepResult
from core.resource_manager import ResourceGuard


class TTSStep(PipelineStep):
    name = "tts_engine"

    async def process(self, ctx):
        script    = ctx.get("script")
        agent_cfg = ctx.get("agent_config", {})
        if not script:
            return StepResult.fail("No script in context")
        async with ResourceGuard("light"):
            loop = asyncio.get_event_loop()
            audio = await loop.run_in_executor(None, _gen_audio,
                script, agent_cfg.get("voice_style", "professional"))
        ctx["audio_path"] = audio or ""
        return StepResult.ok(f"Audio: {audio}")


def _gen_audio(script, voice_style):
    from pipeline.tts_engine import generate_narration
    return generate_narration(script, voice_style)
