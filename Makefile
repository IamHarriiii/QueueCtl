.PHONY: help install dev test lint build clean dashboard docker

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install queuectl
	pip install -e .
	queuectl migrate run
	@echo "\n✅ Installed! Try: queuectl --version"

dev: ## Install with dev + realtime extras
	pip install -e ".[all]"
	queuectl migrate run
	@echo "\n✅ Dev environment ready!"

test: ## Run all tests
	@echo "=== Unit Tests ==="
	python -m pytest tests/test_unit.py -v
	@echo "\n=== Integration Tests ==="
	python tests/test_scenarios.py
	@echo "\n=== Phase 1 ==="
	python tests/test_phase1_enhancements.py
	@echo "\n=== Phase 2 ==="
	python tests/test_phase2.py
	@echo "\n=== Phase 3 ==="
	python tests/test_phase3.py

test-quick: ## Run unit tests only (fast)
	python -m pytest tests/test_unit.py -v

lint: ## Run linter
	flake8 queuectl/ --max-line-length=120 --exclude=__pycache__

build: ## Build package for PyPI
	pip install build
	python -m build
	@echo "\n✅ Package built in dist/"

dashboard: ## Launch web dashboard
	queuectl dashboard

docker: ## Build and run with Docker
	docker-compose up -d
	@echo "\n✅ Dashboard: http://localhost:5000"

clean: ## Remove build artifacts and cache
	rm -rf build/ dist/ *.egg-info .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "✅ Cleaned"
