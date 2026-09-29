# Convenience wrappers around Docker Compose and common backend commands.
# Run `make help` to list targets. Requires Docker Compose v2 (the `docker compose` plugin —
# not the standalone Python `docker-compose` v1, which doesn't understand
# `condition: service_completed_successfully` in docker-compose.yml).

.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help up down restart logs ps build \
        migrate makemigration seed-demo create-user \
        backend-shell test lint fmt typecheck check clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS=":.*## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

up: ## Start every service in the background
	$(COMPOSE) up --build -d

down: ## Stop and remove containers (data volumes are kept)
	$(COMPOSE) down

restart: ## Restart the backend and worker (e.g. after an .env change)
	$(COMPOSE) restart backend worker

logs: ## Follow logs for every service
	$(COMPOSE) logs -f

ps: ## Show running services
	$(COMPOSE) ps

build: ## Rebuild images without starting containers
	$(COMPOSE) build

migrate: ## Apply Alembic migrations against the running dev database
	$(COMPOSE) exec backend alembic upgrade head

makemigration: ## Autogenerate a migration from model changes — usage: make makemigration m="add x"
	$(COMPOSE) exec backend alembic revision --autogenerate -m "$(m)"

seed-demo: ## Create one demo user per role (development only)
	$(COMPOSE) exec backend python -m app.cli seed-demo

create-user: ## Create a user — usage: make create-user email=a@b.com name="A B" role=admin
	$(COMPOSE) exec backend python -m app.cli create-user --email "$(email)" --name "$(name)" --role "$(role)"

backend-shell: ## Open a shell in the running backend container
	$(COMPOSE) exec backend bash

test: ## Run the backend test suite inside Docker (against the real db/redis containers)
	$(COMPOSE) exec backend pytest

lint: ## Run ruff (lint only)
	$(COMPOSE) exec backend ruff check .

fmt: ## Auto-format backend code with ruff
	$(COMPOSE) exec backend ruff format .

typecheck: ## Run mypy
	$(COMPOSE) exec backend mypy app

check: lint typecheck test ## Run lint + typecheck + tests (what CI runs)

clean: ## Stop containers AND delete volumes (⚠ deletes local db/redis/upload data)
	$(COMPOSE) down -v
