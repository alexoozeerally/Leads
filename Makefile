.PHONY: install migrate api dashboard test lint format run-sample up down

install:
	uv sync --extra dev
	uv run playwright install chromium

migrate:
	uv run alembic upgrade head

api:
	uv run uvicorn app.main:app --reload

dashboard:
	uv run streamlit run app/dashboard/streamlit_app.py

run-sample:
	uv run leadfinder run-sample

test:
	uv run pytest -q

lint:
	uv run ruff check app tests
	uv run black --check app tests

format:
	uv run ruff check --fix app tests
	uv run black app tests

up:
	docker compose -f docker/docker-compose.yml up --build

down:
	docker compose -f docker/docker-compose.yml down
