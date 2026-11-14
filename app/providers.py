"""모델 제공자. Gemini SDK 는 이 파일에서만 import 한다 (AI-3).

generate(prompt) 는 글을 돌려주고, json_mode=True 이면 JSON 문자열을 돌려달라고 요청한다.
"""
from typing import Protocol

from .config import Config, ConfigError


class QuotaExceeded(Exception):
    """사용량 한도 초과 (429). 다시 보내도 같은 결과라 재시도하지 않고 바로 대체 문장으로 넘어간다."""


class LLMProvider(Protocol):
    def generate(self, prompt: str, *, json_mode: bool = False) -> str: ...


class GeminiProvider:
    def __init__(self, api_key: str, model: str, timeout_s: float = 20.0):
        try:
            from google import genai
            from google.genai import types
        except ImportError as e:  # SDK 가 없으면 설치 안내
            raise ConfigError("google-genai 가 필요합니다: pip install -r requirements.txt") from e
        self._types = types
        self._model = model
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),  # 밀리초
        )

    def _thinking_config(self):
        """짧은 대사·요약이라 생각(thinking)을 최소로 해야 빠르고 싸다.
        - 2.5 Flash: thinking_budget=0 으로 끈다.
        - Gemini 3 계열(3.8 Flash 등): 끌 수 없고 thinking_level 로 줄인다. 3.8·3.7 Flash 는 'minimal'을 지원하지 않아
          (오류) 모든 3 계열이 지원하는 가장 낮은 값 'low'를 쓴다.
        - 설치된 SDK 가 thinking_level 을 모르면(오래된 버전) 설정 없이 보낸다 (기본값으로 동작)."""
        if self._model.startswith("gemini-2.5-flash"):
            return self._types.ThinkingConfig(thinking_budget=0)
        if self._model.startswith("gemini-3"):
            try:
                return self._types.ThinkingConfig(thinking_level="low")
            except (TypeError, ValueError):
                return None
        return None

    def generate(self, prompt: str, *, json_mode: bool = False) -> str:
        # 생각(thinking) 토큰이 출력 한도를 먹어 빈 답이 나오지 않도록 한도를 넉넉히 둔다
        options = {"temperature": 0.8, "max_output_tokens": 2048}
        if json_mode:
            options["response_mime_type"] = "application/json"
        thinking = self._thinking_config()
        if thinking is not None:
            options["thinking_config"] = thinking
        # 함수 호출 기능은 쓰지 않는다 (SDK 의 AFC 경고 문구도 사라진다)
        options["automatic_function_calling"] = self._types.AutomaticFunctionCallingConfig(disable=True)
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=self._types.GenerateContentConfig(**options),
            )
        except Exception as e:
            if _is_quota_error(e):
                raise QuotaExceeded() from None  # 원문(요청 내용 포함 가능)은 버린다
            raise
        return response.text or ""


def _is_quota_error(e: Exception) -> bool:
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    return code == 429 or "RESOURCE_EXHAUSTED" in str(e)


class FakeProvider:
    """네트워크 없이 정해 둔 글을 돌려주는 제공자. 테스트·로컬 개발용.

    reply 가 리스트이면 호출할 때마다 차례대로 돌려주고, 끝나면 마지막 값을 반복한다.
    """

    def __init__(self, reply: "str | list[str]" = "연습에 꾸준히 참여하고 있어요. 다음에는 놓친 단서를 함께 살펴봐요."):
        self.reply = reply
        self.calls = 0
        self.last_prompt: str | None = None

    def generate(self, prompt: str, *, json_mode: bool = False) -> str:
        self.calls += 1
        self.last_prompt = prompt
        if isinstance(self.reply, list):
            return self.reply[min(self.calls, len(self.reply)) - 1]
        return self.reply


def build_provider(cfg: Config) -> LLMProvider:
    if cfg.provider == "fake":
        return FakeProvider()
    return GeminiProvider(api_key=cfg.gemini_api_key, model=cfg.gemini_model)
