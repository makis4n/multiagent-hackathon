.PHONY: sync check lint typecheck test fixture evals ui format

sync:
	uv sync --all-packages

check: lint typecheck test

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run basedpyright

test:
	uv run pytest

fixture:
	uv run trip --fixture tokyo --auto-confirm

evals:
	uv run python evals/run.py

ui:
	uv run streamlit run apps/agent/trip_agent/ui.py

format:
	uv run ruff format .
	uv run ruff check --fix .
