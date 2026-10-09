# Contributing to Quantum Compute (SN 48)

Thank you for contributing! This guide covers development setup, testing, linting, and the contribution process.

## Development Setup

### 1. Clone and enter the repository

```bash
git clone https://github.com/qbittensor-labs/quantum-compute.git
cd quantum-compute
```

### 2. Create a Python virtual environment (3.12+ required)

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows use `.venv\Scripts\activate`.

### 3. Install the package in editable (`-e`) mode

```bash
pip install -e .
```

**This step is critical.** The editable install:

- Makes the `qbittensor` package importable from your source checkout.
- Ensures local code changes take effect immediately without reinstalls.
- Is required for correct resolution of local data directories when running neurons.

See `qbittensor/database/database_manager.py` for notes on `DATA_DIR` resolution.

Operator guides (install + run):

- [qbittensor/miner/README.md](qbittensor/miner/README.md)
- [qbittensor/validator/README.md](qbittensor/validator/README.md)

### 4. Install development dependencies

```bash
pip install -r requirements-dev.txt
```

This pulls in `pytest` (for tests) and `flake8` (for linting).

## Running Tests

```bash
# Run the default test suite
pytest .

# Verbose
pytest -v
```

Configuration lives in [pytest.ini](pytest.ini):

- Tests are discovered under `tests/`
- `qbittensor/miner/` is excluded from recursion
- Default warning filters are applied

## Linting

The project uses [flake8](https://flake8.pycqa.org/) with custom settings defined in [.flake8](.flake8) (120 char line length).

```bash
flake8 .
```

Fix all violations before submitting a PR. The CI pipeline will fail if `flake8` reports any issues.

## Continuous Integration

All pushes and pull requests to `main` run the workflow defined in [.github/workflows/ci.yml](.github/workflows/ci.yml):

1. Checkout
2. Setup Python 3.12
3. `pip install -e .`
4. `pip install -r requirements-dev.txt`
5. `flake8 .`
6. `pytest ...` (with JUnit results + publishing to PRs)

A passing CI run (lint + tests) is required for merge.

## Pull Request Guidelines

- Branch from `main` (or the current development branch).
- Keep changes focused and reasonably sized.
- Run `flake8 .` and `pytest .` locally and confirm they pass.
- Update documentation (README, docstrings, etc.) when behavior changes.
- Reference related issues in the PR description.

## Additional Development Notes

- **Environment variables**: Loaded via `python-dotenv` through `qbittensor.utils.env.load_env()` / `get_api_config()` (same pattern as enigma-staging). Create a local **`.env`** in the repo root as needed (gitignored; never commit secrets). Common variables:
  - `JOB_SERVER_URL` (job/platform API base URL)
  - `TENSORAUTH_URL`
  - `METRICS_API_URL` (telemetry)
  - `API_VERSION`
  - `DATA_DIR` / `PROVIDER` (optional)
  - Override path with `ENV_FILE` or `DOTENV_PATH` if needed
- **Database paths**: The neurons reliably use `DATA_DIR` (or the `--neuron.data_dir` flag) for placing SQLite files. An editable install (`pip install -e .`) of the checkout you are developing in is the most reliable setup.
- **CI behavior**: CI injects a dummy `JOB_SERVER_URL`.

## Questions?

Open an issue or reach out on the [Discord](https://discord.gg/bittensor).
