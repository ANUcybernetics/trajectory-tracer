import json
import logging
from pathlib import Path
from uuid import UUID

import typer

import trajectory_tracer.engine as engine
from trajectory_tracer.db import (
    count_invocations,
    create_db_and_tables,
    get_session_from_connection_string,
    latest_experiment,
    list_experiments,
    list_runs,
)
from trajectory_tracer.embeddings import list_models as list_embedding_models
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


@app.command("perform-experiment")
def perform_experiment(
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

        # Handle seed_count if present
        if "seed_count" in config_data:
            seed_count = config_data.pop("seed_count")
            config_data["seeds"] = [-1] * seed_count
            logger.info(f"Using seed_count={seed_count}, generated {seed_count} seeds with value -1")

        # Create database engine and tables
        db_str = f"sqlite:///{db_path}"
        logger.info(f"Creating/connecting to database at {db_path}")

        # Call the create_db_and_tables function
        create_db_and_tables(db_str)

        # Create experiment config from JSON and save to database
        with get_session_from_connection_string(db_str) as session:
            config = ExperimentConfig(**config_data)
            session.add(config)
            session.commit()
            session.refresh(config)

            # Calculate total number of runs that will be generated
            total_runs = len(config.networks) * len(config.seeds) * len(config.prompts)

            logger.info(
                f"Configuration loaded successfully: {len(config.networks)} networks, "
                f"{len(config.seeds)} seeds, {len(config.prompts)} prompts, "
                f"for a total of {total_runs} runs"
            )

            # Get the config ID to pass to the engine
            config_id = str(config.id)

        # Run the experiment
        logger.info(f"Starting experiment with config ID: {config_id}")
        engine.perform_experiment(config_id, db_str)

        logger.info(f"Experiment completed successfully. Results saved to {db_path}")
    except Exception as e:
        logger.error(f"Early termination of experiment: {e}")
        raise typer.Exit(code=1)


@app.command("list-experiments")
def list_experiments_command(
    db_path: Path = typer.Option(
        "output/db/trajectory_data.sqlite",
        "--db-path",
        "-d",
        help="Path to the SQLite database file",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show full experiment details"
    ),
):
    """
    List all experiments stored in the database.

    Displays experiment IDs and basic information about each experiment.
    Use --verbose for more detailed output.
    """
    try:
        # Create database connection
        db_str = f"sqlite:///{db_path}"
        logger.info(f"Connecting to database at {db_path}")

        # List all experiments using the function from db module
        with get_session_from_connection_string(db_str) as session:
            experiments = list_experiments(session)

            if not experiments:
                typer.echo("No experiments found in the database.")
                return

            typer.echo(f"Found {len(experiments)} experiments:")

            for experiment in experiments:
                run_count = len(experiment.runs)

                if verbose:
                    # Detailed output
                    typer.echo(f"\nExperiment ID: {experiment.id}")
                    typer.echo(f"  Started: {experiment.started_at}")
                    typer.echo(f"  Completed: {experiment.completed_at}")
                    typer.echo(f"  Networks: {len(experiment.networks)}")
                    typer.echo(f"  Seeds: {len(experiment.seeds)}")
                    typer.echo(f"  Prompts: {len(experiment.prompts)}")
                    typer.echo(f"  Embedding models: {experiment.embedding_models}")
                    typer.echo(f"  Max length: {experiment.max_length}")
                    typer.echo(f"  Runs: {run_count}")
                else:
                    # Simple output
                    elapsed = (experiment.completed_at - experiment.started_at).total_seconds()
                    typer.echo(
                        f"{experiment.id} - runs: {run_count}, "
                        f"max_length: {experiment.max_length}, "
                        f"started: {experiment.started_at.strftime('%Y-%m-%d %H:%M')}, "
                        f"elapsed: {elapsed:.1f}s"
                    )

    except Exception as e:
        logger.error(f"Error listing experiments: {e}")
        raise typer.Exit(code=1)


@app.command("experiment-status")
def experiment_status(
    experiment_id: str = typer.Argument(
        None,
        help="ID of the experiment to check status for (defaults to the most recent experiment)",
    ),
    db_path: Path = typer.Option(
        "output/db/trajectory_data.sqlite",
        "--db-path",
        "-d",
        help="Path to the SQLite database file",
    ),
):
    """
    Get the status of a trajectory tracer experiment.

    Shows the progress of the experiment, including invocation, embedding, and
    persistence diagram completion percentages.
    """
    # Create database connection
    db_str = f"sqlite:///{db_path}"
    logger.info(f"Connecting to database at {db_path}")

    # Get the experiment and print status
    with get_session_from_connection_string(db_str) as session:
        experiment = None

        if experiment_id is None or experiment_id.lower() == "latest":
            experiment = latest_experiment(session)
            if not experiment:
                logger.error("No experiments found in the database")
                raise typer.Exit(code=1)
            logger.info(f"Using latest experiment with ID: {experiment.id}")
        else:
            experiment = session.get(ExperimentConfig, UUID(experiment_id))
            if not experiment:
                logger.error(f"Experiment with ID {experiment_id} not found")
                raise typer.Exit(code=1)

        experiment.print_status()


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
        db_str = f"sqlite:///{db_path}"
        logger.info(f"Connecting to database at {db_path}")

        # List all runs
        with get_session_from_connection_string(db_str) as session:
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

    # Group models by output type
    models_by_type = {}
    for model_name in list_genai_models():
        output_type = get_output_type(model_name).value
        if output_type not in models_by_type:
            models_by_type[output_type] = []
        models_by_type[output_type].append(model_name)

    # Print models grouped by output type
    for output_type, models in models_by_type.items():
        typer.echo(f"\n  Output Type: {output_type}")
        for model_name in models:
            typer.echo(f"    {model_name}")

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
        db_str = f"sqlite:///{db_path}"
        logger.info(f"Connecting to database at {db_path}")

        # Get the run and export images
        with get_session_from_connection_string(db_str) as session:
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
        db_str = f"sqlite:///{db_path}"
        # Iterate over all runs, printing only those with stop reason ("duplicate", loop_length)
        with get_session_from_connection_string(db_str) as session:
            # Get the requested runs by ID
            run_ids = ['067e39a7-91ce-766b-bf5e-0a79502d904c', '067e39a7-91e3-7c8f-83f9-83c287302678']
            for run_id in run_ids:
                try:
                    run = session.get(Run, UUID(run_id))
                    if not run:
                        logger.info(f"Run with ID {run_id} not found")
                        continue

                    # Count embeddings
                    embedding_count = len(run.embeddings)
                    logger.info(f"Run {run_id}: {embedding_count} embeddings")

                    # Count and describe persistence diagrams
                    pd_count = len(run.persistence_diagrams)

                    if pd_count > 0:
                        logger.info(f"Run {run_id}: {pd_count} persistence diagrams:")
                        for i, pd in enumerate(run.persistence_diagrams):
                            generators = pd.get_generators_as_arrays()
                            logger.info(f"  - PD #{i+1}: using {pd.embedding_model} model, {len(generators)} generators")
                    else:
                        logger.info(f"Run {run_id}: No persistence diagrams")

                except ValueError as e:
                    logger.error(f"Invalid run ID format: {e}")
        logger.info("Script execution completed")

    except Exception as e:
        logger.error(f"Error executing script: {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
