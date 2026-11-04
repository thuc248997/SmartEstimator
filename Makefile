.PHONY: build up down logs test migrate seed shell lint

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

dev:
	docker compose run --rm --service-ports api python manage.py runserver 0.0.0.0:8000

logs:
	docker compose logs -f api worker

test:
	docker compose run --rm api pytest -q

migrate:
	docker compose run --rm api python manage.py migrate

seed:
	docker compose run --rm api python manage.py seed_sample

shell:
	docker compose run --rm api python manage.py shell

lint:
	docker compose run --rm api ruff check .
