import pytest

from app.config import Config, ConfigError, load_dotenv


def test_load_dotenv_parses_values(tmp_path):
    f = tmp_path / ".env"
    f.write_text(
        '# 주석\n\nAI_PORT=9000   # 뒤 주석\nGEMINI_API_KEY="abc 123"\nAI_HOST = 0.0.0.0\n',
        encoding="utf-8",
    )
    env = {}
    load_dotenv(f, env)
    assert env == {"AI_PORT": "9000", "GEMINI_API_KEY": "abc 123", "AI_HOST": "0.0.0.0"}


def test_load_dotenv_does_not_override_existing_env(tmp_path):
    f = tmp_path / ".env"
    f.write_text("AI_PORT=9000\n", encoding="utf-8")
    env = {"AI_PORT": "7000"}
    load_dotenv(f, env)
    assert env["AI_PORT"] == "7000"


def test_load_dotenv_missing_file_is_ok(tmp_path):
    env = {}
    load_dotenv(tmp_path / "nope.env", env)
    assert env == {}


def test_placeholder_key_counts_as_missing():
    env = {"AI_INTERNAL_TOKEN": "t", "AI_PROVIDER": "gemini", "GEMINI_API_KEY": "여기에 키값을 넣으시오"}
    with pytest.raises(ConfigError):
        Config.from_env(env)
    assert Config.from_env({**env, "AI_PROVIDER": "fake"}).gemini_api_key is None
