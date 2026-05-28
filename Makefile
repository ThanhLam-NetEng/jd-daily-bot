.PHONY: install test compile run dry-run docker-build docker-run security

install:
	python -m pip install -r requirements.txt

compile:
	python -m py_compile scripts/fetch_jd.py

test: compile
	python -m pytest -q

run:
	python scripts/fetch_jd.py

dry-run:
	DRY_RUN=1 python scripts/fetch_jd.py

docker-build:
	docker build -t jd-daily-bot .

docker-run:
	docker compose run --rm jd-daily-bot

security:
	python -m pip install pip-audit bandit
	python -m pip_audit
	python -m bandit -q -r scripts
