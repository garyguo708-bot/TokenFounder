.PHONY: test test-v install

install:
	uv sync

test:
	PYTHONPATH=.. uv run pytest tests/

test-v:
	PYTHONPATH=.. uv run pytest tests/ -v
