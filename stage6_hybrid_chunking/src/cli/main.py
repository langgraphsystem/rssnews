"""
CLI entry point for Stage 6 Hybrid Chunking system.
"""

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from src.config.settings import Settings
from src.utils.logging import configure_logging

# Create Typer app
app = typer.Typer(
    name="stage6",
    help="Stage 6 Hybrid Chunking CLI - Production-grade article chunking with selective LLM refinement",
    rich_markup_mode="rich"
)

console = Console()


def version_callback(value: bool):
    """Show version information."""
    if value:
        console.print("Stage 6 Hybrid Chunking v1.0.0")
        console.print("Production-grade article processing with Gemini 2.5 Flash")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", "-v",
        callback=version_callback,
        help="Show version information"
    ),
    config_file: Optional[Path] = typer.Option(
        None, "--config", "-c",
        help="Configuration file path"
    ),
    verbose: bool = typer.Option(
        False, "--verbose",
        help="Enable verbose logging"
    ),
    log_format: str = typer.Option(
        "console", "--log-format",
        help="Log format: console or json"
    )
):
    """
    Stage 6 Hybrid Chunking CLI.
    
    Process articles through deterministic base chunking with selective LLM refinement
    using Gemini 2.5 Flash API for production workloads.
    """
    # Configure logging
    log_level = "DEBUG" if verbose else "INFO"
    configure_logging(log_level=log_level, log_format=log_format, enable_tracing=True)
    
    if config_file:
        console.print(f"Using config file: {config_file}")


def run_async(coro):
    """Helper to run async functions in CLI commands."""
    return asyncio.run(coro)


# Import commands to register them with the app
from src.cli import commands  # noqa


if __name__ == "__main__":
    app()