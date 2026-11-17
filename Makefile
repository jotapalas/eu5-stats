.DEFAULT_GOAL := help
SHELL := /bin/bash
COMPOSE ?= docker compose
URL ?= http://localhost:8000
SAVE ?=

.PHONY: help build up down logs backend-logs web-logs test shell db-shell decode token-stats campaign session \
	reprocess web-shell web-lint web-test web-build web-prod-up

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

build: ## Build the Docker images
	$(COMPOSE) build

up: ## Start the API (port 8000) and the frontend dev server (port 5173) in the background
	$(COMPOSE) up -d

down: ## Stop all services
	$(COMPOSE) --profile prod down

logs: ## Follow logs of all services
	$(COMPOSE) logs -f

backend-logs: ## Follow API logs
	$(COMPOSE) logs -f api

web-logs: ## Follow frontend dev server logs
	$(COMPOSE) logs -f web

test: ## Run the test suite inside the container
	$(COMPOSE) run --rm api pytest $(ARGS)

shell: ## Open a bash shell in the container
	$(COMPOSE) run --rm api bash

db-shell: ## Open sqlite3 on the stats database
	$(COMPOSE) run --rm api sqlite3 data/eu5stats.db

decode: ## Decode a save via the running API: make decode SAVE=file.eu5 [PARAMS='sections=metadata']
	@test -n "$(SAVE)" || (echo "Usage: make decode SAVE=<file.eu5>"; exit 1)
	curl -sSf -F "file=@$(SAVE)" "$(URL)/decode?$(PARAMS)" -o "$(SAVE).json"
	@echo "Wrote $(SAVE).json"

token-stats: ## Show unresolved native tokens across all saves
	$(COMPOSE) run --rm api python -m tools.token_stats . saves tests/fixtures $(ARGS)

campaign: ## Create a campaign: make campaign NAME="My campaign" [DESC="..."]
	@test -n "$(NAME)" || (echo 'Usage: make campaign NAME="..."'; exit 1)
	curl -sSf -X POST -H 'Content-Type: application/json' \
		-d "$$(python3 -c 'import json,sys; print(json.dumps({"name": sys.argv[1], "description": sys.argv[2] or None}))' "$(NAME)" "$(DESC)")" \
		"$(URL)/campaigns"; echo

session: ## Upload a session's saves: make session CAMPAIGN=<id> DIR=<folder> [NAME=...] [PLAYED_ON=YYYY-MM-DD]
	@test -n "$(CAMPAIGN)" -a -n "$(DIR)" || (echo "Usage: make session CAMPAIGN=<id> DIR=<folder>"; exit 1)
	@set -e; shopt -s nullglob; args=(); \
	for f in "$(DIR)"/*.eu5; do args+=(-F "files=@$$f"); done; \
	test $${#args[@]} -gt 0 || { echo "No .eu5 files in $(DIR)"; exit 1; }; \
	if [ -n "$(NAME)" ]; then args+=(-F "name=$(NAME)"); fi; \
	if [ -n "$(PLAYED_ON)" ]; then args+=(-F "played_on=$(PLAYED_ON)"); fi; \
	curl -sSf "$${args[@]}" "$(URL)/campaigns/$(CAMPAIGN)/sessions"; echo

reprocess: ## Re-extract every save of a campaign: make reprocess CAMPAIGN=<id>
	@test -n "$(CAMPAIGN)" || (echo "Usage: make reprocess CAMPAIGN=<id>"; exit 1)
	curl -sSf -X POST "$(URL)/campaigns/$(CAMPAIGN)/reprocess"; echo

web-shell: ## Open a shell in the frontend container
	$(COMPOSE) run --rm web sh

web-lint: ## Type-check and lint the frontend
	$(COMPOSE) run --rm web sh -c "npm install --no-fund --no-audit && npm run typecheck && npm run lint"

web-test: ## Run the frontend unit tests (vitest)
	$(COMPOSE) run --rm web sh -c "npm install --no-fund --no-audit && npm test -- $(ARGS)"

web-build: ## Build the production frontend image (nginx)
	$(COMPOSE) --profile prod build web-prod

web-prod-up: ## Serve the production frontend on port 8080
	$(COMPOSE) --profile prod up -d web-prod
