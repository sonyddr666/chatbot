.PHONY: help install dev test lint run serve frontend-dev docker-up clean

help:
	@echo "Comandos disponíveis:"
	@echo "  install      Instala dependências Python"
	@echo "  dev          Instala dependências de desenvolvimento"
	@echo "  test         Roda testes Python"
	@echo "  lint         Roda linter (ruff)"
	@echo "  run          Roda CLI interativa"
	@echo "  serve        Roda servidor API (porta 8000)"
	@echo "  frontend-dev Roda frontend em dev (porta 3000)"
	@echo "  docker-up    Sobe todos serviços com Docker Compose"
	@echo "  clean        Limpa arquivos temporários"

install:
	pip install -r requirements.txt

dev: install
	pip install pytest ruff black

test:
	pytest tests/ -v

lint:
	ruff check src/ tests/
	black --check src/ tests/

run:
	python -m src.main chat

serve:
	python -m src.main serve

frontend-dev:
	cd frontend && npm run dev

docker-up:
	docker-compose up --build -d

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf frontend/dist
