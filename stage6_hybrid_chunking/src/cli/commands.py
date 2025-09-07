"""
CLI commands for Stage 6 processing.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel
from rich.tree import Tree
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.cli.main import app, run_async
from src.config.settings import Settings
from src.db.models import Article
from src.stage6.pipeline import Stage6Pipeline
from src.stage6.processor import ChunkProcessor, BatchConfiguration
from src.stage6.coordinator import BatchCoordinator, JobPriority
from src.utils.metrics import InMemoryMetrics, Stage6Metrics
from src.utils.health import create_stage6_health_checker, HealthStatus
from src.utils.tracing import initialize_tracing
from sqlalchemy import select

console = Console()


async def get_database_session(settings: Settings) -> AsyncSession:
    """Create database session."""
    engine = create_async_engine(
        settings.database_url,
        echo=settings.db.echo_sql,
        pool_size=settings.db.pool_size,
        max_overflow=settings.db.max_overflow,
        pool_timeout=settings.db.pool_timeout
    )
    
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return async_session()


@app.command()
def process_articles(
    article_ids: List[int] = typer.Option(
        None, "--article-id", "-a",
        help="Article IDs to process (can specify multiple)"
    ),
    source_domain: Optional[str] = typer.Option(
        None, "--source-domain", "-s",
        help="Process articles from specific source domain"
    ),
    batch_size: int = typer.Option(
        50, "--batch-size", "-b",
        help="Batch size for processing"
    ),
    max_articles: int = typer.Option(
        1000, "--max-articles", "-m",
        help="Maximum number of articles to process"
    ),
    priority: str = typer.Option(
        "normal", "--priority", "-p",
        help="Job priority: urgent, high, normal, low"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Show what would be processed without actually processing"
    ),
    use_coordinator: bool = typer.Option(
        True, "--use-coordinator/--direct",
        help="Use coordinator for job management or process directly"
    )
):
    """
    Process articles through Stage 6 hybrid chunking pipeline.
    
    Examples:
    \b
        # Process specific articles
        stage6 process-articles -a 123 -a 456 -a 789
        
        # Process articles from domain
        stage6 process-articles --source-domain example.com --max-articles 100
        
        # High priority processing
        stage6 process-articles --source-domain news.com --priority high
        
        # Dry run to see what would be processed
        stage6 process-articles --source-domain test.com --dry-run
    """
    run_async(_process_articles(
        article_ids, source_domain, batch_size, max_articles, 
        priority, dry_run, use_coordinator
    ))


async def _process_articles(
    article_ids: List[int],
    source_domain: Optional[str],
    batch_size: int,
    max_articles: int,
    priority: str,
    dry_run: bool,
    use_coordinator: bool
):
    """Async implementation of process_articles command."""
    
    # Load settings
    settings = Settings()
    
    # Initialize tracing if enabled
    if settings.observability.tracing_enabled:
        initialize_tracing(
            service_name="stage6-cli",
            jaeger_endpoint=getattr(settings, 'jaeger_endpoint', None)
        )
    
    # Create database session
    db_session = await get_database_session(settings)
    
    try:
        # Find articles to process
        if article_ids:
            query = select(Article).where(Article.id.in_(article_ids))
            console.print(f"Processing {len(article_ids)} specific articles")
        elif source_domain:
            query = select(Article).where(Article.source_domain == source_domain).limit(max_articles)
            console.print(f"Processing articles from domain: {source_domain} (max: {max_articles})")
        else:
            query = select(Article).limit(max_articles)
            console.print(f"Processing {max_articles} latest articles")
        
        result = await db_session.execute(query)
        articles = result.scalars().all()
        
        if not articles:
            console.print("[yellow]No articles found to process[/yellow]")
            return
        
        # Show articles to be processed
        table = Table(title=f"Articles to Process ({len(articles)})")
        table.add_column("ID", style="cyan")
        table.add_column("Title", style="magenta", max_width=50)
        table.add_column("Domain", style="green")
        table.add_column("Language", style="blue")
        table.add_column("Published", style="dim")
        
        for article in articles[:10]:  # Show first 10
            table.add_row(
                str(article.id),
                article.title[:47] + "..." if len(article.title) > 50 else article.title,
                article.source_domain,
                article.language or "unknown",
                article.published_at.strftime("%Y-%m-%d %H:%M") if article.published_at else "unknown"
            )
        
        if len(articles) > 10:
            table.add_row("...", f"and {len(articles) - 10} more", "", "", "")
        
        console.print(table)
        
        if dry_run:
            console.print("[green]Dry run completed - no articles were processed[/green]")
            return
        
        # Map priority
        priority_map = {
            "urgent": JobPriority.URGENT,
            "high": JobPriority.HIGH, 
            "normal": JobPriority.NORMAL,
            "low": JobPriority.LOW
        }
        job_priority = priority_map.get(priority.lower(), JobPriority.NORMAL)
        
        console.print(f"\n[bold]Starting processing with priority: {priority}[/bold]")
        
        if use_coordinator:
            await _process_with_coordinator(articles, settings, db_session, batch_size, job_priority)
        else:
            await _process_directly(articles, settings, db_session)
        
    finally:
        await db_session.close()


async def _process_with_coordinator(articles, settings, db_session, batch_size, priority):
    """Process articles using the coordinator."""
    
    # Create batch configuration
    batch_config = BatchConfiguration(
        batch_size=batch_size,
        max_concurrent_batches=3,
        retry_failed_articles=True
    )
    
    # Create coordinator
    coordinator = BatchCoordinator(settings, db_session, batch_config)
    
    try:
        # Submit job
        article_ids = [article.id for article in articles]
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            
            task = progress.add_task("Submitting job...", total=1)
            
            job_id = await coordinator.submit_job(
                article_ids,
                priority=priority,
                context={"cli_processing": True}
            )
            
            progress.update(task, completed=1)
            progress.add_task("Processing articles...", total=len(articles))
            
            console.print(f"\n[green]Job submitted: {job_id}[/green]")
            
            # Monitor job progress
            while True:
                await asyncio.sleep(2)
                
                status = await coordinator.get_job_status(job_id)
                if not status:
                    break
                
                if status['status'] == 'completed':
                    console.print(f"[green]Job completed successfully![/green]")
                    if status.get('result'):
                        result = status['result']
                        console.print(f"Processed: {result.get('processed_articles', 0)} articles")
                        console.print(f"Processing time: {result.get('processing_time_ms', 0):.1f}ms")
                    break
                elif status['status'] == 'failed':
                    console.print(f"[red]Job failed: {status.get('error_message', 'Unknown error')}[/red]")
                    break
                elif status['status'] == 'running':
                    console.print("Job is running...", end="\r")
    
    finally:
        await coordinator.cleanup()


async def _process_directly(articles, settings, db_session):
    """Process articles directly without coordinator."""
    
    # Create processor
    processor = ChunkProcessor(settings, db_session)
    
    try:
        article_ids = [article.id for article in articles]
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            
            task = progress.add_task("Processing articles...", total=len(articles))
            
            result = await processor.process_articles(
                article_ids,
                processing_context={"cli_direct_processing": True}
            )
            
            progress.update(task, completed=len(articles))
            
            # Show results
            console.print("\n[green]Processing completed![/green]")
            console.print(f"Processed articles: {result['processed_articles']}")
            console.print(f"Failed articles: {result['failed_articles']}")
            console.print(f"Processing time: {result['processing_time_ms']:.1f}ms")
            
            if result.get('errors'):
                console.print(f"[red]Errors: {len(result['errors'])}[/red]")
                for error in result['errors'][:5]:  # Show first 5 errors
                    console.print(f"  - {error}")
    
    finally:
        await processor.cleanup()


@app.command()
def health_check(
    timeout: int = typer.Option(
        5, "--timeout", "-t",
        help="Health check timeout in seconds"
    ),
    detailed: bool = typer.Option(
        False, "--detailed", "-d",
        help="Show detailed health check results"
    )
):
    """
    Run comprehensive health checks on all system components.
    
    Examples:
    \b
        # Quick health check
        stage6 health-check
        
        # Detailed health check with longer timeout
        stage6 health-check --detailed --timeout 10
    """
    run_async(_health_check(timeout, detailed))


async def _health_check(timeout: int, detailed: bool):
    """Async implementation of health_check command."""
    
    settings = Settings()
    db_session = await get_database_session(settings)
    
    try:
        # Create Gemini client if enabled
        gemini_client = None
        if settings.features.llm_chunk_refine_enabled:
            from src.llm.gemini_client import GeminiClient
            gemini_client = GeminiClient(settings)
        
        # Create health checker
        health_checker = create_stage6_health_checker(
            db_session=db_session,
            gemini_client=gemini_client,
            timeout_seconds=timeout
        )
        
        console.print("[bold]Running health checks...[/bold]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            
            task = progress.add_task("Checking system health...", total=None)
            
            # Run all health checks
            results = await health_checker.check_all()
            
            progress.update(task, completed=1)
        
        # Get overall health
        overall_health = health_checker.get_overall_health()
        
        # Display results
        console.print("\n[bold]Health Check Results[/bold]")
        
        # Overall status
        status_color = {
            HealthStatus.HEALTHY: "green",
            HealthStatus.DEGRADED: "yellow", 
            HealthStatus.UNHEALTHY: "red",
            HealthStatus.UNKNOWN: "blue"
        }
        
        console.print(
            Panel(
                f"Overall Status: [{status_color[overall_health]}]{overall_health.value.upper()}[/{status_color[overall_health]}]",
                title="System Health"
            )
        )
        
        # Individual check results
        table = Table(title="Component Health")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Duration", style="dim")
        
        if detailed:
            table.add_column("Message", style="italic", max_width=40)
        
        for name, result in results.items():
            status_style = status_color[result.status]
            
            row = [
                name.replace('_', ' ').title(),
                f"[{status_style}]{result.status.value}[/{status_style}]",
                f"{result.duration_ms:.1f}ms"
            ]
            
            if detailed:
                row.append(result.message[:37] + "..." if len(result.message) > 40 else result.message)
            
            table.add_row(*row)
        
        console.print(table)
        
        if detailed and any(result.details for result in results.values()):
            console.print("\n[bold]Details:[/bold]")
            
            tree = Tree("Health Check Details")
            for name, result in results.items():
                if result.details:
                    component_tree = tree.add(f"{name}: {result.status.value}")
                    for key, value in result.details.items():
                        component_tree.add(f"{key}: {value}")
            
            console.print(tree)
        
        # Cleanup
        if gemini_client:
            await gemini_client.close()
    
    finally:
        await db_session.close()


@app.command()
def status(
    watch: bool = typer.Option(
        False, "--watch", "-w",
        help="Watch status continuously"
    ),
    interval: int = typer.Option(
        5, "--interval", "-i",
        help="Watch interval in seconds"
    )
):
    """
    Show system status and metrics.
    
    Examples:
    \b
        # Show current status
        stage6 status
        
        # Watch status continuously
        stage6 status --watch --interval 3
    """
    if watch:
        run_async(_watch_status(interval))
    else:
        run_async(_show_status())


async def _show_status():
    """Show current system status."""
    
    settings = Settings()
    db_session = await get_database_session(settings)
    
    try:
        # Create metrics collector
        metrics = InMemoryMetrics()
        
        # Create pipeline for status
        pipeline = Stage6Pipeline(settings, db_session, metrics)
        
        # Get status
        status = await pipeline.get_pipeline_status()
        
        console.print("[bold]Stage 6 Pipeline Status[/bold]")
        
        # System info
        info_table = Table(title="System Information")
        info_table.add_column("Setting", style="cyan")
        info_table.add_column("Value", style="magenta")
        
        info_table.add_row("Environment", settings.environment.value)
        info_table.add_row("Target Words", str(settings.chunking.target_words))
        info_table.add_row("LLM Enabled", str(status['llm_enabled']))
        info_table.add_row("Active Batches", str(status['active_batches']))
        info_table.add_row("Articles Processed", str(status['total_articles_processed']))
        info_table.add_row("Chunks Created", str(status['total_chunks_created']))
        
        console.print(info_table)
        
        # Component status
        component_table = Table(title="Component Status")
        component_table.add_column("Component", style="cyan")
        component_table.add_column("Status", style="bold")
        
        for component, comp_status in status['components'].items():
            status_color = "green" if comp_status == "healthy" else "yellow" if "degraded" in comp_status else "red"
            component_table.add_row(
                component.replace('_', ' ').title(),
                f"[{status_color}]{comp_status}[/{status_color}]"
            )
        
        console.print(component_table)
        
        # Metrics if available
        if 'gemini_stats' in status:
            stats = status['gemini_stats']
            metrics_table = Table(title="LLM API Metrics")
            metrics_table.add_column("Metric", style="cyan")
            metrics_table.add_column("Value", style="magenta")
            
            metrics_table.add_row("Total Requests", str(stats.get('total_requests', 0)))
            metrics_table.add_row("Total Tokens", str(stats.get('total_tokens', 0)))
            metrics_table.add_row("Circuit Breaker", stats.get('circuit_breaker_state', 'unknown'))
            
            console.print(metrics_table)
        
        await pipeline.cleanup()
    
    finally:
        await db_session.close()


async def _watch_status(interval: int):
    """Watch status continuously."""
    
    try:
        while True:
            console.clear()
            console.print(f"[dim]Status updated at {datetime.now().strftime('%H:%M:%S')} (refreshing every {interval}s)[/dim]\n")
            
            await _show_status()
            
            console.print(f"\n[dim]Press Ctrl+C to stop watching[/dim]")
            
            await asyncio.sleep(interval)
    
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped watching[/yellow]")


@app.command()  
def worker(
    queue: str = typer.Option(
        "default", "--queue", "-q",
        help="Celery queue to process"
    ),
    concurrency: int = typer.Option(
        4, "--concurrency", "-c",
        help="Number of concurrent workers"
    ),
    log_level: str = typer.Option(
        "INFO", "--log-level", "-l",
        help="Log level for worker"
    )
):
    """
    Start Celery worker for processing jobs.
    
    Examples:
    \b
        # Start default worker
        stage6 worker
        
        # Start worker for specific queue
        stage6 worker --queue stage6_processing --concurrency 8
    """
    
    console.print(f"[bold]Starting Celery worker[/bold]")
    console.print(f"Queue: {queue}")
    console.print(f"Concurrency: {concurrency}")
    console.print(f"Log Level: {log_level}")
    
    # Import and start Celery worker
    from src.celery_app import celery_app
    
    # Start worker (this blocks)
    celery_app.worker_main([
        'worker',
        '--loglevel', log_level.lower(),
        '--concurrency', str(concurrency),
        '--queues', queue
    ])


@app.command()
def migrate(
    revision: Optional[str] = typer.Option(
        None, "--revision", "-r",
        help="Target revision (latest if not specified)"
    ),
    sql: bool = typer.Option(
        False, "--sql",
        help="Show SQL instead of executing"
    )
):
    """
    Run database migrations.
    
    Examples:
    \b
        # Run all pending migrations
        stage6 migrate
        
        # Migrate to specific revision  
        stage6 migrate --revision abc123
        
        # Show SQL without executing
        stage6 migrate --sql
    """
    run_async(_migrate(revision, sql))


async def _migrate(revision: Optional[str], sql: bool):
    """Run database migrations."""
    
    try:
        from alembic.config import Config
        from alembic import command
        
        # Configure Alembic
        alembic_cfg = Config("alembic.ini")
        
        if sql:
            console.print("[bold]SQL Preview:[/bold]")
            command.upgrade(alembic_cfg, revision or "head", sql=True)
        else:
            console.print("[bold]Running database migrations...[/bold]")
            command.upgrade(alembic_cfg, revision or "head")
            console.print("[green]Migrations completed successfully[/green]")
    
    except ImportError:
        console.print("[red]Alembic not installed. Install with: pip install alembic[/red]")
    except Exception as e:
        console.print(f"[red]Migration failed: {e}[/red]")