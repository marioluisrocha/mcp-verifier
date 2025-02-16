"""Command-line interface for MCP server verification."""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress

from mcp_verifier.core.verification import VerificationGraph
from mcp_verifier.core.models import VerificationResult

app = typer.Typer()
console = Console()

def display_result(result: VerificationResult):
    """Display verification results in a formatted table."""
    # Display overall status
    if result.approved:
        console.print("\n[green]✓ Verification Passed![/green]")
    else:
        console.print("\n[red]✗ Verification Failed![/red]")
        
    # Security Issues
    if result.security_issues:
        console.print("\n[bold]Security Issues:[/bold]")
        table = Table(show_header=True)
        table.add_column("Severity")
        table.add_column("Location")
        table.add_column("Description")
        table.add_column("Recommendation")
        
        for issue in result.security_issues:
            table.add_row(
                f"[{'red' if issue.severity == 'high' else 'yellow' if issue.severity == 'medium' else 'blue'}]{issue.severity}[/]",
                issue.location,
                issue.description,
                issue.recommendation
            )
        console.print(table)
        
    # Guideline Violations
    if result.guideline_violations:
        console.print("\n[bold]Guideline Violations:[/bold]")
        table = Table(show_header=True)
        table.add_column("Rule")
        table.add_column("Description")
        table.add_column("Impact")
        
        for violation in result.guideline_violations:
            table.add_row(
                violation.rule,
                violation.description,
                violation.impact
            )
        console.print(table)
        
    # Description Match
    console.print(f"\n[bold]Description Match:[/bold] {result.description_match:.1%}")

@app.command()
def verify(
    server_path: Path = typer.Argument(
        ..., 
        help="Path to MCP server directory",
        exists=True,
        dir_okay=True,
        file_okay=False
    ),
    description: str = typer.Option(
        ...,
        "--description", "-d",
        help="Server description to verify against"
    ),
    config: Optional[Path] = typer.Option(
        None,
        "--config", "-c",
        help="Path to config file",
        exists=True,
        dir_okay=False,
        file_okay=True
    )
):
    """Verify an MCP server implementation."""
    try:
        # Create verifier
        verifier = VerificationGraph()
        
        # Run verification with progress
        with Progress() as progress:
            task = progress.add_task("Verifying server...", total=5)
            
            async def run_verification():
                result = await verifier.verify(
                    str(server_path),
                    description,
                    config=config
                )
                progress.update(task, advance=1)
                return result
                
            # Run verification
            result = asyncio.run(run_verification())
            
            # Display results
            display_result(result)
            
            # Exit with appropriate code
            sys.exit(0 if result.approved else 1)
            
    except Exception as e:
        console.print(f"[red]Error during verification: {str(e)}[/red]")
        sys.exit(1)

if __name__ == "__main__":
    app()