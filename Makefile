.PHONY: install lint fmt test collect
install:
	pip install -e ".[dev]"
lint:
	ruff check . && ruff format --check . && mypy
fmt:
	ruff check --fix . && ruff format .
test:
	pytest
collect:
	transitpulse collect --feed vbb --once
