# IntelliYaml

![PyPI version](https://img.shields.io/pypi/v/intelliyaml.svg)
[![Documentation Status](https://readthedocs.org/projects/intelliyaml/badge/?version=latest)](https://intelliyaml.readthedocs.io/en/latest/?version=latest)

IntelliYaml adds a small layer on top of PyYAML for configuration files that need environment-variable expansion, dynamic Python object references, and dataclass-backed YAML values.

- PyPI package: https://pypi.org/project/intelliyaml/
- Free software: MIT License
- Documentation: https://intelliyaml.readthedocs.io

## Features

- `YamlObjectLoader` reads YAML mappings with PyYAML `FullLoader` and resolves `!!python/object:...` mappings into Python objects.
- Object resolution supports attribute access, method calls, callable targets, chained operations, indexing, literal values, expression strings, and common binary operators such as `/` for path joins.
- `YamlEnvVariableExpander` expands `${VAR}` and `${VAR:-default}` expressions in strings and nested data structures.
- `yamldataclass` wraps `dataclasses.dataclass` and registers PyYAML load/dump callbacks for a custom YAML tag.
- Console scripts `intelliyaml` and `yaml` parse a YAML file and print the resulting mapping.

## Requirements

IntelliYaml requires Python 3.13 or newer.

## Installation

```sh
uv add intelliyaml
```

Or with `pip`:

```sh
pip install intelliyaml
```

## Quick Start

Create a YAML file that resolves an object:

```yaml
log_file: !!python/object:pathlib.Path
  chain:
    - call: null
      args: ["/tmp"]
    - op: "/"
      value: "app.log"
```

Load it with `YamlObjectLoader`:

```python
from pathlib import Path

from intelliyaml import YamlObjectLoader

with YamlObjectLoader(Path("config.yaml")) as config:
    print(config.data["log_file"])
```

The context manager reads the file on entry and writes a sibling `.backup.yaml` copy of the original file on exit.

For string expansion without a file:

```python
from intelliyaml import YamlEnvVariableExpander

value = YamlEnvVariableExpander.expand_string("token=${API_TOKEN:-local}")
```

## CLI

The installed console scripts parse a YAML file and print the parsed mapping:

```sh
intelliyaml config.yaml
yaml config.yaml
```

## Safety

Only use `YamlObjectLoader` with trusted YAML. The `!!python/object:...` constructor can import Python modules and resolve attributes, callables, methods, operators, and indexes from the loaded YAML document.

## Documentation

- [Installation](docs/installation.md)
- [Usage](docs/usage.md)
- [API reference](docs/api.md)
- [Contributing](CONTRIBUTING.md)
- [History](HISTORY.md)
