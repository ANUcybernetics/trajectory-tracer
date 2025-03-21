import json
import logging
from pathlib import Path
from uuid import UUID

import typer

from trajectory_tracer.db import count_invocations, get_database, list_runs, read_run
from trajectory_tracer.embeddings import list_models as list_embedding_models
from trajectory_tracer.engine import perform_experiment, create_persistence_diagram, perform_persistence_diagram, create_embedding, perform_embedding
from trajectory_tracer.genai_models import get_output_type
from trajectory_tracer.genai_models import list_models as list_genai_models
from trajectory_tracer.schemas import ExperimentConfig, Run
from trajectory_tracer.utils import export_run_images

# NOTE: all these logging shenanigans are required because it's not otherwise
# possible to shut pyvips (a dep of moondream) up

# Set up logging first, before any handlers might be added by other code
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Create a special NullHandler that will silently discard all VIPS messages
class VIPSNullHandler(logging.Handler):
    def emit(self, record):
        pass

# Create a separate logger for VIPS messages
vips_logger = logging.Logger("VIPS")
vips_logger.addHandler(VIPSNullHandler())
vips_logger.propagate = False  # Don't propagate to root logger

# Store the original getLogger method
original_getLogger = logging.getLogger

# Define a replacement getLogger that catches VIPS loggers
def patched_getLogger(name=None):
    if name == "VIPS" or (isinstance(name, str) and "VIPS" in name):
        return vips_logger
    return original_getLogger(name)

# Replace the standard getLogger method
logging.getLogger = patched_getLogger

# Also capture direct root logger messages about VIPS
original_log = logging.Logger._log

def patched_log(self, level, msg, args, exc_info=None, extra=None, stack_info=False):
    if isinstance(msg, str) and "VIPS:" in msg:
        return None  # Skip logging VIPS messages
    return original_log(self, level, msg, args, exc_info, extra, stack_info)

logging.Logger._log = patched_log

# Get a logger for this module
logger = logging.getLogger(__name__)

app = typer.Typer()

@app.command("run-experiment")
def run_experiment(
    config_file: Path = typer.Argument(
        ...,
        help="Path to the configuration JSON file",
        exists=True,
        readable=True,
        file_okay=True,
        dir_okay=False,
    ),
    db_path: Path = typer.Option(
        "output/db/trajectory_data.sqlite",
        "--db-path",
        "-d",
        help="Path to the SQLite database file",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose output"
    ),
):
    """
    Run a trajectory tracer experiment defined in CONFIG_FILE.

    The CONFIG_FILE should be a JSON file containing experiment parameters that can be
    parsed into an ExperimentConfig object.
    """
    # Configure logging based on verbosity
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load configuration
    logger.info(f"Loading configuration from {config_file}")

    try:
        with open(config_file, "r") as f:
            config_data = json.load(f)

        # Create experiment config from JSON
        config = ExperimentConfig(**config_data)
        logger.info(
            f"Configuration loaded successfully: {len(config.networks)} networks, "
            f"{len(config.seeds)} seeds, {len(config.prompts)} prompts"
        )

        # Create database engine and tables
        db_url = f"sqlite:///{db_path}"
        logger.info(f"Creating/connecting to database at {db_path}")

        # Get database instance with the specified path
        database = get_database(connection_string=db_url)

        # Run the experiment
        with database.get_session() as session:
            logger.info("Starting experiment...")
            perform_experiment(config=config, session=session)

        logger.info(f"Experiment completed successfully. Results saved to {db_path}")

    except Exception as e:
        logger.error(f"Early termination of experiment: {e}")
        raise typer.Exit(code=1)


@app.command("list-runs")
def list_runs_command(
    db_path: Path = typer.Option(
        "output/db/trajectory_data.sqlite",
        "--db-path",
        "-d",
        help="Path to the SQLite database file",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show full run details"
    ),
):
    """
    List all runs stored in the database.

    Displays run IDs and basic information about each run.
    Use --verbose for more detailed output.
    """
    try:
        # Create database connection
        db_url = f"sqlite:///{db_path}"
        logger.info(f"Connecting to database at {db_path}")
        database = get_database(connection_string=db_url)

        # List all runs
        with database.get_session() as session:
            runs = list_runs(session)

            if not runs:
                typer.echo("No runs found in the database.")
                return

            for run in runs:
                if verbose:
                    # Detailed output
                    typer.echo(f"\nRun ID: {run.id}")
                    typer.echo(f"  Network: {run.network}")
                    typer.echo(f"  Initial prompt: {run.initial_prompt}")
                    typer.echo(f"  Seed: {run.seed}")
                    typer.echo(f"  Length: {len(run.invocations)}")
                    typer.echo(f"  Stop reason: {run.stop_reason}")
                else:
                    # Simple output
                    typer.echo(
                        f"{run.id} (seed {run.seed}) - length: {len(run.invocations)}/{run.max_length}, stop reason: {run.stop_reason}"
                    )
            typer.echo(
                f"Found {len(runs)} runs ({count_invocations(session)} invocations in total):"
            )

    except Exception as e:
        logger.error(f"Error listing runs: {e}")
        raise typer.Exit(code=1)


@app.command("list-models")
def list_models():
    """
    List all available GenAI and embedding models with their output types.

    This is useful when creating experiment configurations and you need to know
    what models are available and their expected output types.
    """

    typer.echo("## Available GenAI Models:")

    # List GenAI models using the helper function
    for model_name in list_genai_models():
        output_type = get_output_type(model_name).value
        typer.echo(f"  {model_name:<15} (output: {output_type})")

    typer.echo("\n## Available Embedding Models:")

    # List embedding models using the helper function
    for model_name in list_embedding_models():
        typer.echo(f"  {model_name}")


@app.command("export-images")
def export_images(
    run_id: str = typer.Argument(
        ...,
        help="ID of the run to export images from (or 'all' to export from all runs)",
    ),
    output_dir: str = typer.Option(
        "output/images",
        "--output-dir",
        "-o",
        help="Directory where images will be saved",
    ),
    db_path: Path = typer.Option(
        "output/db/trajectory_data.sqlite",
        "--db-path",
        "-d",
        help="Path to the SQLite database file",
    ),
):
    """
    Export all image invocations from a run to JPEG files with embedded metadata.

    Images are saved to the specified output directory with metadata embedded in EXIF.
    If 'all' is specified as the run_id, exports images from all runs in the database.
    """
    try:
        # Create database connection
        db_url = f"sqlite:///{db_path}"
        logger.info(f"Connecting to database at {db_path}")
        database = get_database(connection_string=db_url)

        # Get the run and export images
        with database.get_session() as session:
            runs = []

            if run_id.lower() == "all":
                # Export images from all runs
                runs = list_runs(session)
                if not runs:
                    logger.info("No runs found in the database")
                    raise typer.Exit(code=0)
                logger.info(f"Exporting images for all {len(runs)} runs")
            else:
                # Find the run by ID
                try:
                    run = session.get(Run, UUID(run_id))
                    if not run:
                        logger.error(f"Run with ID {run_id} not found")
                        raise typer.Exit(code=1)
                    runs = [run]
                except ValueError as e:
                    logger.error(f"Invalid run ID format: {e}")
                    raise typer.Exit(code=1)

            # Process all runs (either the single run or all runs)
            for run in runs:
                run_output_dir = f"{output_dir}/{run.id}"
                logger.info(f"Exporting images for run {run.id} to {run_output_dir}")
                export_run_images(run=run, session=session, output_dir=run_output_dir)

        logger.info(f"Image export completed successfully to {run_output_dir}")

    except Exception as e:
        logger.error(f"Error exporting images: {e}")
        raise typer.Exit(code=1)


@app.command("script")
def script(
    db_path: Path = typer.Option(
        "output/db/trajectory_data.sqlite",
        "--db-path",
        "-d",
        help="Path to the SQLite database file",
    ),
):
    """
    Execute a Python script in the context of the application.

    This provides access to the application's database and other utilities,
    allowing for quick development and testing of scripts without needing to set up
    the environment manually.
    """
    try:
        # Create database connection
        db_url = f"sqlite:///{db_path}"
        database = get_database(connection_string=db_url)

        # Example script code - Fetch and print run info
        with database.get_session() as session:
            run = read_run(UUID("067d8ada-9d90-70c2-b71e-da6b9c94fe24"), session)
            logger.info(f"Run: {run.id}")
            if run.persistence_diagrams:
                for i, pd in enumerate(run.persistence_diagrams):
                    logger.info(f"  Persistence Diagram {i+1} - Embedding Model: {pd.embedding_model}")
                    for j, gen in enumerate(pd.generators):
                        logger.info(f"    Generator {j+1}: {gen}")
            else:
                logger.info("  No persistence diagrams found for this run")
        # persistance_diagram_benchmark_vis(".benchmarks/Linux-CPython-3.12-64bit/0002_pd-timings.json")

        logger.info("Script execution completed")

    except Exception as e:
        logger.error(f"Error executing script: {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
