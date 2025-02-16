"""Main entry point for MCP client."""

import sys
import asyncio
from pathlib import Path
import typer
from rich.console import Console

from .ui.chat import main as chat_main

app = typer.Typer()
console = Console()

@app.command()
def chat(
    config: Path = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to config file with API keys and server definitions"
    )
):
    """Start the MCP chat client."""
    try:
        chat_main()
    except Exception as e:
        console.print(f"[red]Error starting chat client: {str(e)}[/red]")
        sys.exit(1)

if __name__ == "__main__":
    app()