import json
import logging
import os

import polars as pl
from plotnine import (
    aes,
    element_text,
    facet_grid,
    facet_wrap,
    geom_bar,
    geom_boxplot,
    geom_errorbar,
    geom_line,
    geom_point,
    ggplot,
    labs,
    position_dodge,
    scale_x_continuous,
    scale_x_discrete,
    scale_y_continuous,
    theme,
)
from sqlmodel import Session

from trajectory_tracer.analysis import load_runs_df

## visualisation


def save(plot, filename: str) -> str:
    """
    Save a plotnine plot to file formats.

    Args:
        plot: plotnine plot to save
        filename: Path to save the chart

    Returns:
        Path to the saved file
    """
    # Ensure output directory exists
    output_dir = os.path.dirname(filename)
    os.makedirs(output_dir, exist_ok=True)

    # Save the plot with high resolution
    plot.save(filename, dpi=300, verbose=False)

    return filename


def create_persistence_diagram_chart(df: pl.DataFrame):
    """
    Create a base persistence diagram chart for a single run.

    Args:
        df: DataFrame containing run data with persistence homology information

    Returns:
        A plotnine plot object for the persistence diagram
    """
    # Convert polars DataFrame to pandas for plotnine
    pandas_df = df.to_pandas()

    # Extract initial prompt, or indicate if there are multiple prompts
    unique_prompts = df["initial_prompt"].unique()
    if len(unique_prompts) > 1:
        _initial_prompt = "multiple prompts"
    else:
        _initial_prompt = unique_prompts[0]

    # Get entropy values per dimension if they exist
    dim_entropy_pairs = df.select(["homology_dimension", "entropy"]).unique(
        subset=["homology_dimension", "entropy"]
    )

    # Sort by homology dimension and format entropy values
    entropy_values = []
    for row in dim_entropy_pairs.sort("homology_dimension").iter_rows(named=True):
        entropy_values.append(f"{row['homology_dimension']}: {row['entropy']:.3f}")

    # Join entropy values into subtitle
    _subtitle = "Entropy " + ", ".join(entropy_values)

    # Create a scatterplot for the persistence diagram
    plot = (
        ggplot(pandas_df, aes(x="birth", y="persistence", color="homology_dimension"))
        + geom_point(alpha=0.1)
        + scale_x_continuous(name="Feature Appearance", limits=[-0.1, None])
        + scale_y_continuous(name="Feature Persistence", limits=[-0.1, None])
        + labs(color="Dimension")
        + theme(figure_size=(5, 5))  # Roughly equivalent to width/height 300px
    )

    return plot


def plot_persistence_diagram(
    df: pl.DataFrame, output_file: str = "output/vis/persistence_diagram.png"
) -> None:
    """
    Create and save a visualization of a single persistence diagram for the given DataFrame.

    Args:
        df: DataFrame containing run data with persistence homology information
        output_file: Path to save the visualization
    """
    # Create the chart
    plot = create_persistence_diagram_chart(df)

    # Save plot with high resolution
    saved_file = save(plot, output_file)

    logging.info(f"Saved single persistence diagram to {saved_file}")


def plot_persistence_diagram_faceted(
    df: pl.DataFrame,
    output_file: str = "output/vis/persistence_diagram.png",
    num_cols: int = 2,
) -> None:
    """
    Create and save a visualization of persistence diagrams for runs in the DataFrame,
    creating a grid of charts (one per run).

    Args:
        df: DataFrame containing run data with persistence homology information
        output_file: Path to save the visualization
        num_cols: Number of columns in the grid layout
    """
    # Convert polars DataFrame to pandas for plotnine
    pandas_df = df.to_pandas()

    # Create the base plot with faceting
    plot = (
        ggplot(pandas_df, aes(x="birth", y="persistence", color="homology_dimension"))
        + geom_point(alpha=0.1)
        + scale_x_continuous(name="Feature Appearance", limits=[-0.1, None])
        + scale_y_continuous(name="Feature Persistence", limits=[-0.1, None])
        + labs(color="Dimension")
        + facet_grid("text_model ~ image_model", labeller="label_both")
        + theme(figure_size=(12, 8), strip_text=element_text(size=10))
    )

    # Save plot with high resolution
    saved_file = save(plot, output_file)
    logging.info(f"Saved persistence diagrams to {saved_file}")


def plot_persistence_diagram_by_run(
    df: pl.DataFrame,
    cols: int,
    output_file: str = "output/vis/persistence_diagram.png",
    num_cols: int = 2,
) -> None:
    """
    Create and save a visualization of persistence diagrams for runs in the DataFrame,
    creating a grid of charts (one per run).

    Args:
        df: DataFrame containing run data with persistence homology information
        output_file: Path to save the visualization
        num_cols: Number of columns in the grid layout
    """
    # Convert polars DataFrame to pandas for plotnine
    pandas_df = df.to_pandas()

    # Create the base plot with faceting by run_id
    plot = (
        ggplot(pandas_df, aes(x="birth", y="persistence", color="homology_dimension"))
        + geom_point(alpha=0.1)
        + scale_x_continuous(name="Feature Appearance", limits=[-0.1, None])
        + scale_y_continuous(name="Feature Persistence", limits=[-0.1, None])
        + labs(color="Dimension")
        + facet_wrap("~ run_id", ncol=cols, labeller="label_both")
        + theme(figure_size=(16, 10), strip_text=element_text(size=8))
    )

    # Save plot with high resolution
    saved_file = save(plot, output_file)
    logging.info(f"Saved persistence diagrams to {saved_file}")


def create_persistence_entropy_chart(df: pl.DataFrame):
    """
    Create a base boxplot showing the distribution of entropy values
    with homology_dimension on the y-axis.

    Args:
        df: DataFrame containing runs data with homology_dimension and entropy

    Returns:
        A plotnine plot object for the entropy distribution
    """
    # Convert polars DataFrame to pandas for plotnine
    pandas_df = df.to_pandas()

    # Create a boxplot chart
    plot = (
        ggplot(
            pandas_df, aes(x="entropy", y="homology_dimension", fill="embedding_model")
        )
        + geom_boxplot(alpha=0.7, position=position_dodge(width=0.8))
        + scale_x_continuous(name="Persistence Entropy")
        + labs(y="Homology dimension", fill="Embedding model")
        + theme(figure_size=(5, 2))
    )

    return plot


def plot_persistence_entropy(
    df: pl.DataFrame, output_file: str = "output/vis/persistence_entropy.png"
) -> None:
    """
    Create and save a visualization of entropy distribution across different homology dimensions.

    Args:
        df: DataFrame containing runs data with homology_dimension and entropy
        output_file: Path to save the visualization
    """
    # Check if we have the required columns
    required_columns = {"homology_dimension", "entropy"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        logging.info(
            f"Required columns not found in DataFrame: {', '.join(missing_columns)}"
        )
        return

    # If the DataFrame is empty, return early
    if df.is_empty():
        logging.info("ERROR: DataFrame is empty - no entropy data to plot")
        return

    # Create the chart
    plot = create_persistence_entropy_chart(df)

    # Save plot with high resolution
    saved_file = save(plot, output_file)
    logging.info(f"Saved persistence entropy plot to {saved_file}")


def plot_persistence_entropy_faceted(
    df: pl.DataFrame, output_file: str = "output/vis/persistence_entropy_faceted.png"
) -> None:
    """
    Create and save a visualization of entropy distributions with:
    - entropy on x axis
    - homology_dimension on y axis
    - embedding_model as color
    - faceted by text_model (rows) and image_model (columns)

    Args:
        df: DataFrame containing runs data with homology_dimension and entropy
        output_file: Path to save the visualization
    """
    # Check if we have the required columns
    required_columns = {
        "homology_dimension",
        "entropy",
        "embedding_model",
        "text_model",
        "image_model",
    }
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        logging.info(
            f"Required columns not found in DataFrame: {', '.join(missing_columns)}"
        )
        return

    # If the DataFrame is empty, return early
    if df.is_empty():
        logging.info("ERROR: DataFrame is empty - no entropy data to plot")
        return

    # Convert polars DataFrame to pandas for plotnine
    pandas_df = df.to_pandas()

    # Create the base plot with faceting
    plot = (
        ggplot(
            pandas_df, aes(x="entropy", y="homology_dimension", fill="embedding_model")
        )
        + geom_boxplot(alpha=0.7, position=position_dodge(width=0.8))
        + scale_x_continuous(name="Persistence Entropy")
        + labs(y="Homology dimension", fill="Embedding model")
        + facet_grid("text_model ~ image_model", labeller="label_both")
        + theme(figure_size=(12, 8), strip_text=element_text(size=10))
    )

    # Save the plot
    saved_file = save(plot, output_file)
    logging.info(f"Saved faceted persistence entropy plots to {saved_file}")


def plot_loop_length_by_prompt(df: pl.DataFrame, output_file: str) -> None:
    """
    Create a faceted histogram of loop length by initial prompt.

    Args:
        df: a Polars DataFrame
        output_file: Path to save the visualization
    """
    # Filter to only include rows with loop_length
    df_filtered = df.filter(pl.col("loop_length").is_not_null())
    pandas_df = df_filtered.to_pandas()

    # Create faceted histogram chart
    plot = (
        ggplot(pandas_df, aes(x="loop_length"))
        + geom_bar()
        + facet_grid("initial_prompt ~ .")
        + scale_x_continuous(name="Loop Length")
        + labs(y=None)
        + theme(figure_size=(8, 5))
    )

    # Save the plot
    saved_file = save(plot, output_file)
    logging.info(f"Saved loop length plot to {saved_file}")


def plot_semantic_drift(
    df: pl.DataFrame, output_file: str = "output/vis/semantic_drift.png"
) -> None:
    """
    Create a line plot showing semantic drift over sequence number,
    faceted by initial prompt and model.

    Args:
        df: DataFrame containing embedding data with semantic_drift and sequence_number
        output_file: Path to save the visualization
    """
    # Check if we have the required columns
    required_columns = {
        "semantic_drift",
        "sequence_number",
        "run_id",
        "initial_prompt",
        "embedding_model",  # Added for faceting
    }
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        logging.info(
            f"Required columns not found in DataFrame: {', '.join(missing_columns)}"
        )
        return

    # Filter to only include rows with drift measure
    df_filtered = df.filter(pl.col("semantic_drift").is_not_null())
    pandas_df = df_filtered.to_pandas()

    # Create a single chart with faceting
    plot = (
        ggplot(
            pandas_df,
            aes(
                x="sequence_number", y="semantic_drift", color="run_id", group="run_id"
            ),
        )
        + geom_line(alpha=0.9)
        + scale_x_continuous(name="Sequence Number")
        + labs(y="Semantic Drift", color="Run ID")
        + facet_grid("initial_prompt ~ embedding_model")
        + theme(figure_size=(12, 8))
    )

    # Save the chart
    saved_file = save(plot, output_file)
    logging.info(f"Saved semantic drift plot to {saved_file}")


def persistance_diagram_benchmark_vis(benchmark_file: str) -> None:
    """
    Visualize PD (Giotto PH) benchmark data from a JSON file using plotnine.

    Args:
        benchmark_file: Path to the JSON benchmark file
    """
    # Load the benchmark data
    with open(benchmark_file, "r") as f:
        data = json.load(f)

    # Extract benchmark results
    benchmark_data = []
    for benchmark in data["benchmarks"]:
        benchmark_data.append({
            "n_points": benchmark["params"]["n_points"],
            "mean": benchmark["stats"]["mean"],
            "min": benchmark["stats"]["min"],
            "max": benchmark["stats"]["max"],
            "stddev": benchmark["stats"]["stddev"],
        })

    # Convert to DataFrame
    df = pl.DataFrame(benchmark_data)
    pandas_df = df.to_pandas()

    # Create bar chart with error bars
    plot = (
        ggplot(pandas_df, aes(x="n_points", y="mean"))
        + geom_bar(stat="identity")
        + geom_errorbar(aes(ymin="min", ymax="max"), width=0.2)
        + scale_x_discrete(name="Number of Points")
        + labs(y="Time (seconds)", title="Giotto PH wall-clock time")
        + theme(figure_size=(10, 6.67))
    )

    # Save the chart to a file
    saved_file = save(plot, "output/vis/giotto_benchmark.png")
    logging.info(f"Saved Giotto benchmark plot to {saved_file}")


def paper_charts(session: Session) -> None:
    """
    Generate charts for paper publications.
    """
    # embeddings_df = load_embeddings_df(session, use_cache=True)
    # embeddings_df = embeddings_df.filter(
    #     (pl.col("experiment_id") == "067ed16c-e9a4-7bec-9378-9325a6fb10f7")
    #     | (pl.col("experiment_id") == "067ee281-70f5-774a-b09f-e199840304d0")
    # )
    # plot_semantic_drift(embeddings_df, "output/vis/semantic_drift.png")

    runs_df = load_runs_df(session, use_cache=True)
    runs_df = runs_df.filter(
        (pl.col("experiment_id") == "067ed16c-e9a4-7bec-9378-9325a6fb10f7")
        | (pl.col("experiment_id") == "067ee281-70f5-774a-b09f-e199840304d0")
    )
    # plot_persistence_diagram_faceted(runs_df, "output/vis/persistence_diagram_faceted.png")
    # plot_persistence_diagram_by_run(
    #     runs_df, 16, "output/vis/persistence_diagram_by_run.png"
    # )
    plot_persistence_entropy_faceted(
        runs_df, "output/vis/persistence_entropy_faceted.png"
    )
