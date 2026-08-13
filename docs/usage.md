# Usage

Import the public objects from `intelliyaml`:

```python
from intelliyaml import YamlEnvVariableExpander, YamlObjectLoader, yamldataclass
```

## Loading a YAML File

`YamlObjectLoader` is a context manager for YAML configuration files. It reads the file on entry and stores the parsed mapping on `.data`.

```python
from pathlib import Path

from intelliyaml import YamlObjectLoader

with YamlObjectLoader(Path("config.yaml")) as config:
    parsed_config = config.data
```

The context manager writes a sibling `.backup.yaml` file containing the original YAML when it exits.

To parse YAML from a string instead of a file, instantiate the loader and call `load_yaml(data)`:

```python
from intelliyaml import YamlObjectLoader

loader = YamlObjectLoader()
parsed_config = loader.load_yaml("""
path: !!python/object:pathlib.Path
  chain:
    - call: null
      args: ["/tmp"]
    - op: "/"
      value: "app.log"
""")
```

## Resolving Python Objects

Use the `!!python/object:` tag to resolve a Python object. The suffix is either a fully qualified object path or a built-in name.

```yaml
count: !!python/object:int
  call: null
  args: ["3"]

log_file: !!python/object:pathlib.Path
  chain:
    - call: null
      args: ["/tmp"]
    - op: "/"
      value: "app.log"
```

Supported operation keys:

| Key | Meaning |
| --- | --- |
| `get` or `attr` | Read an attribute from the current object. |
| `call` | Call a named method. Use `call: null` to call the current object itself. |
| `args` | Positional arguments for `call`. |
| `kwargs` | Keyword arguments for `call`. |
| `op` | Apply a binary operator to the current object. |
| `value` or `right` | Right-hand value for an operator, or a literal value when used alone. |
| `index` | Index into a mapping or sequence. |
| `chain` | Run a list of operations in order. |
| `expr` | Evaluate a compact expression string against the target object. |
| `debug` or `_debug` | Print resolver steps for troubleshooting. |

Supported binary operators are `/`, `+`, `-`, `*`, `//`, `%`, `**`, `@`, `|`, and `&`.

## Expression Syntax

`expr` is a compact alternative to a `chain` for simple attribute access, calls, indexing, literals, and binary operators.

```yaml
log_file: !!python/object:pathlib.Path
  expr: 'cwd() / "logs" / "app.log"'
```

Expression strings support identifiers, quoted strings, numbers, `.` attribute access, `()` calls, `[]` indexing, and the supported binary operators.

## Environment Variables

`YamlEnvVariableExpander` expands shell-style placeholders:

```python
from intelliyaml import YamlEnvVariableExpander

YamlEnvVariableExpander.expand_string("${APP_ENV:-development}")
```

Supported forms:

| Form | Result |
| --- | --- |
| `${VAR}` | Replaced with the environment variable value when set; left unchanged when unset. |
| `${VAR:-default}` | Replaced with the environment variable value when set; otherwise replaced with `default`. |

The instance method `expand_env_vars(data)` recursively expands strings inside dictionaries, lists, and tuples.

```python
from intelliyaml import YamlEnvVariableExpander

expander = YamlEnvVariableExpander()
expanded = expander.expand_env_vars({
    "host": "${APP_HOST:-localhost}",
    "ports": ["${APP_PORT:-8000}"],
})
```

## YAML Dataclasses

Use `yamldataclass` when you want a dataclass that can be loaded and dumped with a custom YAML tag.

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

print(server.host)
```

The decorator accepts the same common options as `dataclasses.dataclass`, including `frozen`, `slots`, `kw_only`, `order`, and `unsafe_hash`.

## CLI

After installation, both console scripts parse a YAML file and print the parsed mapping:

```sh
intelliyaml config.yaml
yaml config.yaml
```

## Safety

Only load trusted YAML with `YamlObjectLoader`. The object resolver imports modules and can access attributes, call objects, call methods, apply operators, and index into values described by the YAML document.
