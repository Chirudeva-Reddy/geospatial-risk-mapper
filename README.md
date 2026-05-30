# ml-portfolio-template

![Python](https://img.shields.io/badge/python-3.13-blue)
![uv](https://img.shields.io/badge/deps-uv-DE5FE9)
![Ruff](https://img.shields.io/badge/lint-Ruff-D7FF64)
![pyright](https://img.shields.io/badge/types-pyright-yellow)
![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC)
![License](https://img.shields.io/badge/license-MIT-green)

> Standards repo for an ML engineering portfolio. Every project repo is created from this template, so they all share one structure, toolchain, and documentation pattern.

## What this is
A reference scaffold — not an application. It defines the conventions every downstream portfolio repo inherits: clean `src/` layout, typed config, a quality gate, CI, and a consistent docs/README pattern.

## Locked stack
Python 3.13 · uv · Ruff · pyright · pytest · Pydantic v2 / pydantic-settings · FastAPI · Streamlit · Docker · GitHub Actions · MIT.

## What's inside
- `src/project_name/` — package skeleton: typed `config.py`, plus `data` / `train` / `predict` stubs and optional `api.py` (FastAPI) / `app.py` (Streamlit).
- `tests/` — smoke tests wired to coverage.
- `docs/` — `architecture.md`, `model_card_template.md`, `experiment_log_template.md`.
- `docs/README_template.md` — the placeholder README downstream repos copy and fill in.
- `data/README.md` — the "data is documented, not committed" convention.
- Tooling: `pyproject.toml`, `Makefile`, `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, optional `Dockerfile`.

## Start a new project from this template
```bash
# 1. Copy this tree into a new repo, then:
# 2. Rename the package and replace placeholders
#    src/project_name/  ->  src/<snake_package>/
#    {{PROJECT_NAME}} / {{project_slug}} / {{ML_DOMAIN}}  ->  real values
# 3. Use docs/README_template.md as the new repo's README.md
# 4. Delete what you don't need (api.py or app.py, Dockerfile, notebooks/)
# 5. Add project deps:
uv add scikit-learn        # example
uv sync
make check                 # ruff + pyright + pytest must pass
```

## Local quality gate
```bash
uv sync
make check        # lint, typecheck, tests
make run-api      # FastAPI at /health
make run-app      # Streamlit
```

## License
MIT.
