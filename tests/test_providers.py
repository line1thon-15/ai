"""Gemini 제공자: 실제 SDK 대신 가짜 모듈을 끼워 호출 형식만 확인한다 (네트워크 없음)."""
import importlib.util
import sys
import types

import pytest

from app.config import Config, ConfigError
from app.providers import FakeProvider, GeminiProvider, build_provider


def _sdk_installed() -> bool:
    """google-genai 가 설치됐는지. google 패키지 자체가 없으면 find_spec 이 ModuleNotFoundError 를 내므로 잡는다."""
    try:
        return importlib.util.find_spec("google.genai") is not None
    except ModuleNotFoundError:
        return False


@pytest.fixture
def fake_sdk(monkeypatch):
    calls = {}

    class GenerateContentConfig:
        def __init__(self, **kw):
            self.kw = kw

    class ThinkingConfig:
        def __init__(self, **kw):
            self.kw = kw

    class HttpOptions:
        def __init__(self, **kw):
            self.kw = kw

    class AutomaticFunctionCallingConfig:
        def __init__(self, **kw):
            self.kw = kw

    class Models:
        def __init__(self):
            self.text = '{"reply": "안녕"}'

        def generate_content(self, model, contents, config):
            calls.update(model=model, contents=contents, config=config.kw)
            return types.SimpleNamespace(text=self.text)

    class Client:
        def __init__(self, api_key, http_options):
            calls.update(api_key=api_key, timeout=http_options.kw["timeout"])
            self.models = Models()

    genai_types = types.ModuleType("google.genai.types")
    genai_types.GenerateContentConfig = GenerateContentConfig
    genai_types.ThinkingConfig = ThinkingConfig
    genai_types.HttpOptions = HttpOptions
    genai_types.AutomaticFunctionCallingConfig = AutomaticFunctionCallingConfig
    genai = types.ModuleType("google.genai")
    genai.Client = Client
    genai.types = genai_types
    google = types.ModuleType("google")
    google.genai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", genai_types)
    return calls


def test_gemini_request_shape(fake_sdk):
    p = GeminiProvider(api_key="k-1", model="gemini-2.5-flash", timeout_s=5)
    assert p.generate("프롬프트", json_mode=True) == '{"reply": "안녕"}'
    assert fake_sdk["api_key"] == "k-1" and fake_sdk["timeout"] == 5000
    assert fake_sdk["model"] == "gemini-2.5-flash" and fake_sdk["contents"] == "프롬프트"
    assert fake_sdk["config"]["response_mime_type"] == "application/json"
    assert fake_sdk["config"]["thinking_config"].kw == {"thinking_budget": 0}
    assert fake_sdk["config"]["automatic_function_calling"].kw == {"disable": True}


def test_other_models_get_no_thinking_setting(fake_sdk):
    GeminiProvider(api_key="k", model="gemini-3-flash").generate("p")
    assert "thinking_config" not in fake_sdk["config"]
    assert "response_mime_type" not in fake_sdk["config"]


def test_empty_text_becomes_empty_string(fake_sdk):
    p = GeminiProvider(api_key="k", model="gemini-3-flash")
    p._client.models.text = None
    assert p.generate("p") == ""


def test_build_provider_fake():
    assert isinstance(build_provider(Config.from_env({"AI_INTERNAL_TOKEN": "t"})), FakeProvider)


@pytest.mark.skipif(_sdk_installed(), reason="SDK 가 설치된 환경")
def test_missing_sdk_gives_install_hint():
    cfg = Config.from_env({"AI_INTERNAL_TOKEN": "t", "AI_PROVIDER": "gemini", "GEMINI_API_KEY": "k"})
    with pytest.raises(ConfigError, match="pip install"):
        build_provider(cfg)
