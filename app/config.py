"""환경 변수 설정 (AI-2). 비밀값은 repr에 찍히지 않게 한다."""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(RuntimeError):
    pass


DEFAULT_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
PLACEHOLDER = "여기에"  # .env 에 안내 문구가 그대로 남아 있는지 확인용


def load_dotenv(path=DEFAULT_ENV_FILE, environ=None) -> None:
    """KEY=VALUE 형식의 .env 를 읽어 환경 변수에 넣는다. 이미 있는 환경 변수는 덮어쓰지 않는다."""
    environ = os.environ if environ is None else environ
    path = Path(path)
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        environ.setdefault(key.strip(), value)


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    internal_token: str = field(repr=False)
    provider: str
    gemini_api_key: str | None = field(repr=False)
    gemini_model: str

    @classmethod
    def from_env(cls, env=None) -> "Config":
        env = os.environ if env is None else env

        token = (env.get("AI_INTERNAL_TOKEN") or "").strip()
        if not token:
            raise ConfigError("AI_INTERNAL_TOKEN 이 필요합니다 (백엔드가 X-Internal-Token 으로 보내는 값)")

        provider = (env.get("AI_PROVIDER") or "fake").strip().lower()
        if provider not in ("fake", "gemini"):
            raise ConfigError("AI_PROVIDER 는 fake 또는 gemini 여야 합니다")

        key = (env.get("GEMINI_API_KEY") or "").strip() or None
        if key and PLACEHOLDER in key:  # 안내 문구가 그대로 남아 있으면 키가 없는 것으로 본다
            key = None
        if provider == "gemini" and not key:
            raise ConfigError("AI_PROVIDER=gemini 이면 .env 의 GEMINI_API_KEY 에 실제 키를 넣어 주세요")

        try:
            port = int(env.get("AI_PORT") or "8081")
        except ValueError:
            raise ConfigError("AI_PORT 는 숫자여야 합니다") from None

        return cls(
            host=env.get("AI_HOST") or "127.0.0.1",
            port=port,
            internal_token=token,
            provider=provider,
            gemini_api_key=key,
            gemini_model=env.get("GEMINI_MODEL") or "gemini-2.5-flash",
        )
