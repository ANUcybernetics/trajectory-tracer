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
    scale_color_manual,
    scale_x_continuous,
    scale_x_discrete,
    scale_y_continuous,
    theme,
)
from plotnine.options import set_option
from sqlmodel import Session

## datavis

set_option("limitsize", False)


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

    plot = (
        ggplot(
            pandas_df,
            aes(x="birth", y="persistence", color="factor(homology_dimension)"),
        )
        + geom_point(alpha=0.02)
        + labs(
            x="feature appearance", y="feature persistence", color="homology dimension"
        )
        + theme(figure_size=(10, 5))  # Roughly equivalent to width/height 300px
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
    # Create the base plot using the existing function
    plot = create_persistence_diagram_chart(df)

    # Add faceting to the plot
    plot = (
        plot
        + facet_grid("text_model ~ image_model + homology_dimension")
        + theme(figure_size=(15, 5), strip_text=element_text(size=10))
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
        + scale_x_continuous(name="Feature Appearance")
        + scale_y_continuous(name="Feature Persistence")
        + labs(color="Dimension")
        + facet_wrap("~ run_id", ncol=cols)
        + theme(figure_size=(16, 10), strip_text=element_text(size=8))
    )

    # Save plot with high resolution
    saved_file = save(plot, output_file)
    logging.info(f"Saved persistence diagrams to {saved_file}")


def plot_persistence_entropy(
    df: pl.DataFrame, output_file: str = "output/vis/persistence_entropy.png"
) -> None:
    """
    Create and save a visualization of entropy distributions with:
    - entropy on x axis
    - homology_dimension on y axis (treated as a factor)
    - embedding_model as color
    - faceted by text_model (rows) and image_model (columns)

    Args:
        df: DataFrame containing runs data with homology_dimension and entropy
        output_file: Path to save the visualization
    """
    # Convert polars DataFrame to pandas for plotnine
    pandas_df = df.to_pandas()

    # Create the plot with faceting
    # Define subscript translator for x-axis labels
    subscripts = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")

    plot = (
        ggplot(
            pandas_df,
            aes(x="factor(homology_dimension)", y="entropy", fill="embedding_model"),
        )
        # + geom_violin(alpha=0.7, width=0.7)
        + geom_boxplot()
        + labs(x="homology dimension", y="entropy", fill="embedding model")
        + scale_x_discrete(
            labels=lambda x: [f"h{str(val).translate(subscripts)}" for val in x]
        )
        + facet_grid("text_model ~ image_model", labeller="label_both")
        + theme(figure_size=(10, 6), strip_text=element_text(size=10))
    )

    # Save plot with high resolution
    saved_file = save(plot, output_file)
    logging.info(f"Saved persistence entropy plot to {saved_file}")


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
    pandas_df = df.to_pandas()

    # Create a single chart with faceting
    plot = (
        ggplot(
            pandas_df,
            aes(
                x="sequence_number",
                y="semantic_drift_instantaneous",
                color="semantic_drift_instantaneous > 0.5",
            ),
        )
        + geom_line(
            aes(group="run_id"), color="black"
        )  # Add black line connecting points by run_id
        + geom_point(alpha=0.8)
        + scale_color_manual(values=["black", "red"])
        + labs(x="sequence number", y="semantic drift")
        + facet_grid("initial_prompt ~ embedding_model")
        + theme(
            figure_size=(30, 80),
            strip_text=element_text(size=10),
            legend_position="none",
        )
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
    # from trajectory_tracer.analysis import warm_caches
    # warm_caches(session)
    # embeddings_df = load_embeddings_df(session, use_cache=True)
    # plot_semantic_drift(embeddings_df, "output/vis/semantic_drift.png")

    from trajectory_tracer.analysis import load_runs_df

    runs_df = load_runs_df(session, use_cache=True)

    # Count rows for each combination of model types and homology dimension
    model_counts = runs_df.group_by([
        "text_model",
        "image_model",
        "embedding_model",
        "homology_dimension",
    ]).count()
    print("Counts per model combination and homology dimension:")
    model_counts.write_csv("out.csv")

    # from trajectory_tracer.analysis import load_embeddings_df

    # plot_persistence_diagram_faceted(
    #     runs_df, "output/vis/persistence_diagram_faceted.png"
    # )
    # plot_persistence_entropy(runs_df, "output/vis/persistence_entropy.png")
    # plot_persistence_diagram_by_run(
    #     runs_df, 16, "output/vis/persistence_diagram_by_run.png"
    # )
