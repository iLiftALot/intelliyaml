# API Reference

Public imports:

```python
from intelliyaml import YamlEnvVariableExpander, YamlObjectLoader, yamldataclass
```

## `YamlObjectLoader`

`YamlObjectLoader(config_file: Path | None = None)` reads YAML mappings and resolves `!!python/object:...` values with PyYAML `FullLoader`.

Important attributes and methods:

| API | Description |
| --- | --- |
| `.data` | Parsed YAML mapping loaded by `read_config()` or the context manager. |
| `.read_config()` | Read `config_file` and populate `.data`. Returns `self`. |
| `.load_yaml(data: str | None = None)` | Parse a YAML string, or re-parse the current `.data` when `data` is omitted. |
| `.json_str(data: dict | None = None)` | Serialize a mapping, or `.data`, to formatted JSON text. |
| `.json_dict(data: str | None = None)` | Parse JSON text, or the JSON representation of `.data`, into a dictionary. |
| `.replace(values: dict[str, str])` | Replace `{key}` placeholders in the JSON representation of `.data` and return the resulting dictionary. |

As a context manager, `YamlObjectLoader` calls `read_config()` on entry and writes a sibling `.backup.yaml` file containing the original configuration file on exit.

## Object Resolver Operations

The `!!python/object:` constructor resolves the tag suffix to a target object, then applies exactly one operation mapping. Use `chain` to apply multiple operations.

```yaml
log_file: !!python/object:pathlib.Path
  chain:
    - call: null
      args: ["/tmp"]
    - op: "/"
      value: "app.log"
```

Supported operations:

| Operation | Accepted keys | Description |
| --- | --- | --- |
| Attribute | `get`, `attr` | Read an attribute from the current object. |
| Call | `call`, `args`, `kwargs` | Call a named method, or use `call: null` to call the current object. |
| Operator | `op`, `value`, `right` | Apply a supported binary operator. |
| Index | `index` | Read a mapping key or sequence index. |
| Literal | `value` | Return a literal value. |
| Chain | `chain` | Run nested operation mappings in order. |
| Expression | `expr` | Evaluate a compact expression against the target object. |

Each operation mapping must contain exactly one primary operation key.

## `YamlEnvVariableExpander`

`YamlEnvVariableExpander` expands environment placeholders in strings.

```python
from intelliyaml import YamlEnvVariableExpander

YamlEnvVariableExpander.expand_string("${APP_ENV:-development}")
```

Supported placeholders:

| Placeholder | Behavior |
| --- | --- |
| `${VAR}` | Uses the environment value when set; leaves the placeholder unchanged when unset. |
| `${VAR:-default}` | Uses the environment value when set; otherwise uses `default`. |

`expand_env_vars(data)` recursively expands placeholders inside strings, dictionaries, lists, and tuples.

## `yamldataclass`

`yamldataclass` applies `dataclasses.dataclass`, adds `from_yaml` and `to_yaml` callbacks, and registers the class with PyYAML `FullLoader` and `Dumper`.

```python
import yaml

from intelliyaml import yamldataclass

@yamldataclass(yaml_tag="!Server")
class Server:
    host: str
    port: int

server = yaml.load("""
!Server
host: localhost
port: 8000
""", Loader=yaml.FullLoader)
```

When `yaml_tag` is omitted, the default tag is `!ClassName`.

## CLI

The package defines two console scripts:

```sh
intelliyaml config.yaml
yaml config.yaml
```

Both commands parse a YAML file with `YamlObjectLoader` and print the resulting mapping.
