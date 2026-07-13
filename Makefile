.PHONY: install lint format typecheck test check run-api run-app train clean help

help:           ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:        ## Sync env from lockfile
	uv sync

lint:           ## Ruff lint
	uv run ruff check .

format:         ## Ruff format
	uv run ruff format .

typecheck:      ## Pyright
	uv run pyright

test:           ## Pytest + coverage
	uv run pytest

check: lint typecheck test  ## Full local quality gate

train:          ## Train both classifier and regressor models
	@if [ -z "$(FLOOD_PATH)" ]; then \
		echo "Error: FLOOD_PATH not specified."; \
		echo ""; \
		echo "Usage: make train FLOOD_PATH=path/to/shapefile_directory"; \
		echo ""; \
		echo "Example: make train FLOOD_PATH=data/ispra_shapefiles/"; \
		echo ""; \
		echo "For data download instructions, run: make help-data"; \
		exit 1; \
	fi
	@echo "Training models with ISPRA flood data from: $(FLOOD_PATH)"
	uv run python -c "from geo_risk.train import train_and_save_all; train_and_save_all(flood_path='$(FLOOD_PATH)')"

run-api:        ## Serve FastAPI locally (requires trained models)
	uv run uvicorn geo_risk.api:app --reload

run-app:        ## Serve Streamlit locally (requires trained models)
	uv run streamlit run src/geo_risk/app.py

clean:          ## Clean cache and build artifacts
	rm -rf .pytest_cache .ruff_cache .pyright .coverage htmlcov models/

help-data:      ## Show data loading instructions
	@echo "ISPRA Flood Data Setup"
	@echo "====================="
	@echo ""
	@echo "Step 1: Download ISPRA flood hazard shapefiles (3 hazard classes)"
	@echo "   - IdroGEO (recommended): https://idrogeo.isprambiente.it/app/page/open-data"
	@echo "   - Geoportal: https://geodati.gov.it/ (search 'pericolosità idraulica')"
	@echo ""
	@echo "Step 2: Extract all files to a directory"
	@echo "   mkdir -p data/ispra_shapefiles"
	@echo "   unzip -d data/ispra_shapefiles/ downloaded_file.zip"
	@echo ""
	@echo "Step 3: Verify files exist (should contain HPH_*, MPH_*, LPH_* shapefiles)"
	@echo "   ls data/ispra_shapefiles/"
	@echo ""
	@echo "Step 4: Train models"
	@echo "   make train FLOOD_PATH=data/ispra_shapefiles/"
	@echo ""
	@echo "For detailed documentation, see: data/README.md"
