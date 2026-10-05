"""Mock language model: deterministic, obviously synthetic output for pipeline tests."""

from __future__ import annotations

from jdhp_adapters.base import Completion, Prompt, ProviderInfo

INFO = ProviderInfo(
    name="mock",
    kind="llm",
    display_name="Mock language model",
    trains_on_inputs=False,
    self_hosted=True,
    data_region="local",
    note="Development and test only.",
)


class MockLanguageModel:
    info = INFO

    async def complete(self, prompt: Prompt) -> Completion:
        text = f"[mock {prompt.template_version}] {prompt.text}"
        return Completion(
            text=text,
            model="mock-llm",
            model_version="1",
            input_tokens=len(prompt.text.split()),
            output_tokens=len(text.split()),
        )
