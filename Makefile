.PHONY: install test lint run build

install:
	pip install -e ".[dev]"

test:
	pytest -v

lint:
	ruff check .

run:
	uvicorn app.main:app --reload --port 8080

build:
	docker build -t ci-doctor .
