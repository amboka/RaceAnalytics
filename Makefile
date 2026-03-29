SHELL := /bin/bash
COMPOSE := docker compose -f docker-compose.yml

.PHONY: help start stop restart logs ps attach_front attach_back attach_online \
	start_front start_back start_online make_start_front make_start_back \
	make_start_online strat_online submodule-update

help:
	@echo "RaceAnalytics Docker commands"
	@echo "  make start            - Build and start all services (backend, frontend, online)"
	@echo "  make stop             - Stop and remove all services"
	@echo "  make restart          - Restart all services"
	@echo "  make logs             - Follow logs from all services"
	@echo "  make ps               - Show running services"
	@echo "  make attach_front     - Open shell in frontend container"
	@echo "  make attach_back      - Open shell in backend container"
	@echo "  make attach_online    - Open shell in online container"
	@echo "  make start_front      - Start frontend only"
	@echo "  make start_back       - Start backend (SQLite)"
	@echo "  make start_online     - Start online only"
	@echo "  make make_start_front - Alias for start_front"
	@echo "  make make_start_back  - Alias for start_back"
	@echo "  make make_start_online- Alias for start_online"
	@echo "  make strat_online     - Typo-safe alias for start_online"
	@echo "  make submodule-update - Init/update git submodules recursively"

start:
	$(COMPOSE) up -d --build

stop:
	$(COMPOSE) down

restart:
	$(COMPOSE) down
	$(COMPOSE) up -d --build

logs:
	$(COMPOSE) logs -f --tail=200

ps:
	$(COMPOSE) ps

attach_front:
	$(COMPOSE) exec frontend bash

attach_back:
	$(COMPOSE) exec backend bash

attach_online:
	$(COMPOSE) exec online bash

start_front:
	$(COMPOSE) up -d --build frontend

start_back:
	$(COMPOSE) up -d --build backend

start_online:
	$(COMPOSE) up -d --build online

make_start_front: start_front

make_start_back: start_back

make_start_online: start_online

strat_online: start_online

submodule-update:
	git submodule sync --recursive
	git submodule update --init --recursive
