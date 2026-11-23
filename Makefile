.PHONY: setup simulate up down validate lint test clean

setup:
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env from .env.example"; else echo ".env already exists"; fi

simulate:
	PYTHONPATH=src python3 scripts/run_local_pipeline.py

up:
	docker compose up --build -d

down:
	docker compose down

validate:
	docker compose config --quiet
	python3 -c "import glob, json; paths = glob.glob('power-automate/**/*.json', recursive=True) + glob.glob('sharepoint/*.json') + glob.glob('infra/*.json') + glob.glob('samples/emails/*.json'); [json.load(open(p, encoding='utf-8')) for p in paths]; print(f'Validated {len(paths)} JSON artifacts.')"

lint:
	ruff check src tests scripts

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

clean:
	rm -rf src/doc_router/__pycache__ tests/__pycache__ .ruff_cache
