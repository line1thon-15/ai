.PHONY: test run

# 테스트 러너: 전체 테스트(스모크 포함) 실행
test:
	python3 -m pytest

# 로컬 서버 실행 (설정은 ai/.env 에서 읽음, 포트 8081)
run:
	python3 -m app
