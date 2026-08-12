"""Console script for intelliyaml."""

import typer
from rich.console import Console
import typer.completion
from intelliyaml import YamlObjectLoader
from intellipath import Path


app = typer.Typer()
console = Console()
typer.completion.get_completion_inspect_parameters()

@app.command()
def yaml_cli(
    yaml_file: str | None = typer.Argument(..., help="Path to the YAML configuration file."),
):
    """Console script for intelliyaml."""

    yaml_path = Path(yaml_file) if yaml_file else None

    with YamlObjectLoader(yaml_path) as ymlp:
        parsed_config = ymlp.data

    console.print(parsed_config)


if __name__ == "__main__":
    app()
