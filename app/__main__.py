"""실행: python -m app"""
import logging

from .config import Config, ConfigError, load_dotenv
from .providers import build_provider
from .server import App, make_server

log = logging.getLogger("ai.main")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    load_dotenv()  # ai/.env 가 있으면 읽는다 (이미 설정된 환경 변수가 우선)
    try:
        cfg = Config.from_env()
        provider = build_provider(cfg)
    except ConfigError as e:
        raise SystemExit(f"설정 오류: {e}")

    httpd = make_server(App(cfg.internal_token, provider, cfg.provider), cfg.host, cfg.port)
    log.info("AI server listening on %s:%s (provider=%s)", cfg.host, cfg.port, cfg.provider)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
