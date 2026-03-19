.PHONY: help fmt lint test check

PYTHON ?= python3
PYTHONPATH ?= src:vendor
RUFF ?= vendor/bin/ruff

help:
	@echo "Targets:"
	@echo "  fmt    - format with ruff"
	@echo "  lint   - ruff check"
	@echo "  test   - pytest (PYTHONPATH=$(PYTHONPATH))"
	@echo "  check  - lint + test"

fmt:
	$(RUFF) format src tests

lint:
	$(RUFF) check src tests

test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest -q

check: lint test

