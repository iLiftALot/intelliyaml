# Installation

IntelliYaml requires Python 3.13 or newer.

## Stable release

To install IntelliYaml, run this command in your terminal:

```sh
uv add intelliyaml
```

Or if you prefer to use `pip`:

```sh
pip install intelliyaml
```

## From source

The source files for IntelliYaml can be downloaded from the [GitHub repo](https://github.com/iLiftALot/intelliyaml).

Clone the public repository:

```sh
git clone https://github.com/iLiftALot/intelliyaml.git
cd intelliyaml
```

Install the project and development dependencies with `uv`:

```sh
uv sync --dev
```

This checkout uses local editable sources for some sibling packages under `[tool.uv.sources]`. If you are not using that local workspace layout, install those packages from PyPI or adjust the local source paths before syncing.

## Development Checks

```sh
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
```
