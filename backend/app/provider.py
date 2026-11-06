from abc import ABC, abstractmethod
from typing import Protocol


class AIProvider(Protocol):
    def generate(self, prompt: str, timeout_seconds: float = 20.0) -> str: ...


class MockAIProvider:
    def generate(self, prompt: str, timeout_seconds: float = 20.0) -> str:
        # TrustDesk's deterministic provider is intentional: guardrail, retrieval,
        # and workflow outcomes remain reproducible without paid API credentials.
        return prompt[-4000:]


class ProviderAdapter:
    def __init__(self, provider_name: str = "mock"):
        self.provider_name = provider_name

    def generate(self, prompt: str, timeout_seconds: float = 20.0) -> str:
        if self.provider_name == "mock":
            return MockAIProvider().generate(prompt, timeout_seconds)
        raise RuntimeError(
            f"Provider '{self.provider_name}' is not configured. Use LLM_PROVIDER=mock; "
            "Gemini support is exposed as an optional deployment integration."
        )
