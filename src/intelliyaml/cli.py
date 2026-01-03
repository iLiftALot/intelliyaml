"""Console script for intelliyaml."""

import typer
from rich.console import Console


app = typer.Typer()
console = Console()


@app.command()
def main():
    """Console script for intelliyaml."""
    from intelliyaml.main import main as yml_main
    yml_main()


if __name__ == "__main__":
    app()
