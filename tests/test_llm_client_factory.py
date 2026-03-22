"""``LLMClientFactory`` on ``ApexRunContext`` / ``apex_run``."""

from __future__ import annotations

from apex.llm.loader import load_llm_client_from_env
from apex.pipeline.run_context import build_apex_run_context
from tests.fakes import FakeLLMClient


def test_build_apex_run_context_uses_custom_llm_client_factory() -> None:
    instance = FakeLLMClient("fake-factory")

    def factory() -> FakeLLMClient:
        return instance

    ctx = build_apex_run_context(prompt="x", llm_client_factory=factory)
    assert ctx.llm_client_factory() is instance


def test_build_apex_run_context_defaults_to_env_loader() -> None:
    ctx = build_apex_run_context(prompt="x")
    assert ctx.llm_client_factory is load_llm_client_from_env
