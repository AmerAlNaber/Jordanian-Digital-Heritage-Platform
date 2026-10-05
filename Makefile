# Common tasks. Every target runs the same way on a laptop and in CI.
SHELL := /bin/bash
.DEFAULT_GOAL := help

.PHONY: help setup up down logs seed migrate test test-api test-worker test-policies test-web lint fmt typecheck openapi tokens

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

setup: ## Install Python and Node dependencies
	uv sync --all-packages
	pnpm install

up: ## Start the full local stack with seed data
	docker compose up -d --build
	docker compose run --rm seed

down: ## Stop the local stack and remove volumes
	docker compose down -v

logs: ## Follow logs of every service
	docker compose logs -f

seed: ## Ingest the seed book into a running stack
	docker compose run --rm seed

migrate: ## Apply database migrations
	uv run --package jdhp-api alembic -c apps/api/alembic.ini upgrade head

test: test-api test-worker test-policies test-web ## Run every test suite

test-api: ## API, worker and package tests with the 80 percent coverage gate on apps/api
	uv run pytest apps/api/tests apps/worker/tests packages --cov --cov-report=term-missing --cov-report=xml

test-worker: ## Worker tests
	uv run pytest apps/worker/tests

test-policies: ## Cerbos policy compilation and test suites
	cerbos compile policies

test-web: ## Web unit tests
	pnpm --filter @jdhp/web test

lint: ## Lint Python and TypeScript
	uv run ruff check .
	uv run ruff format --check .
	uv run lint-imports
	uv run bandit -c pyproject.toml -r apps packages -q
	pnpm lint
	pnpm format:check

fmt: ## Format everything
	uv run ruff format .
	uv run ruff check --fix .
	pnpm format

typecheck: ## Type-check Python and TypeScript
	uv run mypy apps/api/src apps/worker/src packages/ai-adapters/src packages/metadata/src
	pnpm typecheck

openapi: ## Export the OpenAPI document and regenerate the TypeScript client
	uv run --package jdhp-api python -m jdhp_api.openapi_export packages/schemas/openapi.json
	pnpm --filter @jdhp/schemas generate

tokens: ## Build design tokens to CSS variables and the Tailwind preset
	pnpm --filter @jdhp/design-tokens build
