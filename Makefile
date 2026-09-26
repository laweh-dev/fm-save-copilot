.PHONY: help install run test clean

PYTHON ?= python3
UV ?= uv

help:
	@echo "Usage:"
	@echo "  make install      Install dependencies with UV"
	@echo "  make run          Run the CLI with the local environment"
	@echo "  make run ARGS='squad.html --objective \"win championship\" --tactic gegenpress --out report.html'"
	@echo "  make test         Run the test suite, then a CLI smoke test"
	@echo "  make clean        Remove the local virtualenv and cached files"

install:
	$(UV) sync

run:
	$(UV) run python -m fm_copilot $(ARGS)

test:
	$(UV) run python -m pytest tests/ -q
	$(UV) run python -m fm_copilot --help > /dev/null

clean:
	rm -rf .venv
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
