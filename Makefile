.PHONY: help fmt lint test check

PYTHON ?= python3

help:
	@echo "Targets:"
	@echo "  fmt    - format with ruff"
	@echo "  lint   - ruff check"
	@echo "  test   - pytest (needs runtime deps: pip install -e .)"
	@echo "  check  - lint + test"
	@echo ""
	@echo "Ruff: pip install -e \".[dev]\"  OR  vendored binary at vendor/bin/ruff"

# Prefer `python -m ruff` after `pip install -e ".[dev]"`; fall back to vendored binary (gitignored).
fmt:
	@if $(PYTHON) -c "import ruff" >/dev/null 2>&1; then \
		$(PYTHON) -m ruff format src tests; \
	elif [ -x vendor/bin/ruff ]; then \
		vendor/bin/ruff format src tests; \
	else \
		echo "Missing ruff. Run: pip install -e \".[dev]\""; exit 1; \
	fi

lint:
	@if $(PYTHON) -c "import ruff" >/dev/null 2>&1; then \
		$(PYTHON) -m ruff check src tests; \
	elif [ -x vendor/bin/ruff ]; then \
		vendor/bin/ruff check src tests; \
	else \
		echo "Missing ruff. Run: pip install -e \".[dev]\""; exit 1; \
	fi

test:
	$(PYTHON) -m pytest -q

check: lint test
