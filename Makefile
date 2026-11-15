.PHONY: setup inspect sample build verify dev sources inventory
setup:
	uv sync --locked
	npm --prefix frontend ci
inspect:
	uv run baseline inspect
sample:
	uv run baseline build --sample
build:
	uv run baseline build
verify:
	uv run baseline verify
dev:
	uv run --no-env-file python scripts/with_env.py uvicorn baseline.api:app --host 127.0.0.1 --port 8000 --no-access-log
agent-eval:
	uv run --no-env-file python scripts/with_env.py baseline agent-eval
sources:
	python3 ingest/download.py list
inventory:
	python3 ingest/download.py inventory --check-core

.PHONY: test ingest
test:
	uv run pytest -q
ingest:
	python3 ingest/download.py fetch --group core
