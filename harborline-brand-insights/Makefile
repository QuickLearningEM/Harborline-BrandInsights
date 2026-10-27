.PHONY: install test lint demo demo-up demo-down
install:
	python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
test:
	. .venv/bin/activate && pytest
lint:
	. .venv/bin/activate && ruff check src tests
# Local demo with synthetic data. The admin password is generated on first run and saved
# to data/demo-credentials.txt.
demo:
	scripts/demo-up.sh --foreground
# Same demo, detached so it keeps running after the terminal closes (used by Codespaces).
demo-up:
	scripts/demo-up.sh
demo-down:
	pkill -f "[b]rand-insights serve" || true
