import numpy as np
import pytest
from PIL import Image

from trajectory_tracer.embeddings import embed, list_models
from trajectory_tracer.engine import (
    create_embedding,
    create_invocation,
    create_run,
    perform_embedding,
    perform_invocation,
    perform_run,
)
from trajectory_tracer.schemas import Run


def test_dummy_embedding():
    """Test that the dummy embedding returns a random embedding vector."""
    # Create a sample text string
    sample_text = "Sample output text"

    # Get the embedding using the Dummy model
    embedding_vector = embed("Dummy", sample_text)

    # Check that the embedding has the correct properties
    assert len(embedding_vector) == 768  # Expected dimension

    # Verify that the vector contains random values between 0 and 1
    assert all(0 <= x <= 1 for x in embedding_vector)

    # Get another embedding and verify it's different (random)
    embedding2_vector = embed("Dummy", sample_text)
    # Can't directly compare numpy arrays with !=, use numpy's array_equal instead
    assert not np.array_equal(embedding_vector, embedding2_vector)


@pytest.mark.slow
def test_nomic_text_embedding():
    """Test that the nomic text embedding returns a valid embedding vector."""
    # Create a sample text
    sample_text = "Sample output text"

    # Get the embedding using the actual model
    embedding_vector = embed("Nomic", sample_text)

    # Run it again to verify determinism
    embedding_vector2 = embed("Nomic", sample_text)

    # Check that the embedding has the correct properties
    assert embedding_vector is not None
    assert len(embedding_vector) == 768  # Expected dimension

    # Verify it's a proper embedding vector
    assert embedding_vector.dtype == np.float32
    assert not np.all(embedding_vector == 0)  # Should not be all zeros

    # Verify determinism
    assert np.array_equal(embedding_vector, embedding_vector2)


@pytest.mark.slow
def test_nomic_vision_embedding():
    """Test that the nomic vision embedding returns a valid embedding vector."""
    # Create a sample image (red square)
    image = Image.new("RGB", (100, 100), color="red")

    # Get the embedding using the actual model
    embedding_vector = embed("Nomic", image)

    # Run it again to verify determinism
    embedding_vector2 = embed("Nomic", image)

    # Check that the embedding has the correct properties
    assert embedding_vector is not None
    assert len(embedding_vector) == 768

    # Verify it's a proper embedding vector
    assert embedding_vector.dtype == np.float32
    assert not np.all(embedding_vector == 0)  # Should not be all zeros

    # Verify determinism
    assert np.array_equal(embedding_vector, embedding_vector2)


@pytest.mark.slow
def test_nomic_combined_embedding():
    """Test that the Nomic embedding works for both text and images."""
    # Test with text
    sample_text = "Sample output text"
    text_embedding = embed("Nomic", sample_text)
    text_embedding2 = embed("Nomic", sample_text)

    assert text_embedding is not None
    assert len(text_embedding) == 768
    assert text_embedding.dtype == np.float32

    # Verify determinism for text
    assert np.array_equal(text_embedding, text_embedding2)

    # Test with image
    image = Image.new("RGB", (100, 100), color="green")
    image_embedding = embed("Nomic", image)
    image_embedding2 = embed("Nomic", image)

    assert image_embedding is not None
    assert len(image_embedding) == 768
    assert image_embedding.dtype == np.float32

    # Verify determinism for image
    assert np.array_equal(image_embedding, image_embedding2)


@pytest.mark.slow
def test_jina_clip_text_embedding():
    """Test that the JinaClip embedding returns a valid embedding vector for text."""
    # Create a sample text
    sample_text = "Sample output text"

    # Get the embedding using the actual model
    embedding_vector = embed("JinaClip", sample_text)

    # Run it again to verify determinism
    embedding_vector2 = embed("JinaClip", sample_text)

    # Check that the embedding has the correct properties
    assert embedding_vector is not None
    assert len(embedding_vector) == 768  # Expected dimension

    # Verify it's a proper embedding vector
    assert embedding_vector.dtype == np.float32
    assert not np.all(embedding_vector == 0)  # Should not be all zeros

    # Verify determinism
    assert np.array_equal(embedding_vector, embedding_vector2)


@pytest.mark.slow
def test_jina_clip_image_embedding():
    """Test that the JinaClip embedding returns a valid embedding vector for images."""
    # Create a sample image (blue square)
    image = Image.new("RGB", (100, 100), color="blue")

    # Get the embedding using the actual model
    embedding_vector = embed("JinaClip", image)

    # Run it again to verify determinism
    embedding_vector2 = embed("JinaClip", image)

    # Check that the embedding has the correct properties
    assert embedding_vector is not None
    assert len(embedding_vector) == 768  # Expected dimension

    # Verify it's a proper embedding vector
    assert embedding_vector.dtype == np.float32
    assert not np.all(embedding_vector == 0)  # Should not be all zeros

    # Verify determinism
    assert np.array_equal(embedding_vector, embedding_vector2)


def test_create_and_perform_embedding_nomic(db_session):
    """Test creating and performing embedding with Nomic model."""

    # First create a run
    run = Run(
        network=["DummyT2I"],
        seed=42,
        max_length=1,
        initial_prompt="This is a test run"
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    # Create an invocation with output
    input_text = "This is a test for Nomic embedding"
    invocation = create_invocation(
        model="DummyT2I",
        input=input_text,
        run_id=run.id,  # Provide the run_id
        sequence_number=0,
        session=db_session,
        seed=42,
    )
    invocation = perform_invocation(invocation, input_text, db_session)

    # Create and perform the embedding
    embedding = create_embedding("Nomic", invocation, db_session)
    embedding = perform_embedding(embedding, db_session)

    # Check embedding properties
    assert embedding.vector is not None
    assert len(embedding.vector) == 768
    assert embedding.embedding_model == "Nomic"
    assert embedding.started_at is not None
    assert embedding.completed_at is not None
    assert embedding.completed_at >= embedding.started_at


def test_create_and_perform_embedding_jinaclip(db_session):
    """Test creating and performing embedding with JinaClip model."""

    # First create a run
    run = Run(
        network=["DummyT2I"],
        seed=42,
        max_length=1,
        initial_prompt="This is a test run"
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    # Create an invocation with output
    input_text = "This is a test for JinaClip embedding"
    invocation = create_invocation(
        model="DummyT2I",
        input=input_text,
        run_id=run.id,  # Provide the run_id
        sequence_number=0,
        session=db_session,
        seed=42,
    )
    invocation = perform_invocation(invocation, input_text, db_session)

    # Create and perform the embedding
    embedding = create_embedding("JinaClip", invocation, db_session)
    embedding = perform_embedding(embedding, db_session)

    # Check embedding properties
    assert embedding.vector is not None
    assert len(embedding.vector) == 768
    assert embedding.embedding_model == "JinaClip"
    assert embedding.started_at is not None
    assert embedding.completed_at is not None
    assert embedding.completed_at >= embedding.started_at


def test_run_embeddings_by_model(db_session):
    """Test the Run.embeddings_by_model method returns embeddings with a specific model."""

    # Create a run with create_run function
    run = create_run(
        network=["DummyT2I", "DummyI2T"],
        initial_prompt="Test prompt",
        seed=42,
        max_length=2,
        session=db_session,
    )

    # Perform the run to create the invocations
    run = perform_run(run, db_session)

    # Get the invocations that were created
    invocations = run.invocations
    assert len(invocations) >= 2
    invocation1 = invocations[0]
    invocation2 = invocations[1]

    # Create embeddings with different models
    embedding1_1 = create_embedding("Dummy", invocation1, db_session)
    embedding1_1 = perform_embedding(embedding1_1, db_session)

    embedding1_2 = create_embedding("Dummy2", invocation1, db_session)
    embedding1_2 = perform_embedding(embedding1_2, db_session)

    embedding2_1 = create_embedding("Dummy", invocation2, db_session)
    embedding2_1 = perform_embedding(embedding2_1, db_session)

    # Refresh the run object to ensure relationships are loaded
    db_session.refresh(run)

    # Test filtering by model name
    dummy_embeddings = run.embeddings_by_model("Dummy")
    dummy2_embeddings = run.embeddings_by_model("Dummy2")

    # Verify the filtering works correctly
    assert len(dummy_embeddings) == 2
    assert len(dummy2_embeddings) == 1
    assert all(e.embedding_model == "Dummy" for e in dummy_embeddings)
    assert all(e.embedding_model == "Dummy2" for e in dummy2_embeddings)

    # Verify embeddings are associated with the correct invocations
    assert any(e.invocation_id == invocation1.id for e in dummy_embeddings)
    assert any(e.invocation_id == invocation2.id for e in dummy_embeddings)
    assert all(e.invocation_id == invocation1.id for e in dummy2_embeddings)

    # Verify embeddings have valid vectors
    assert all(e.vector is not None and len(e.vector) > 0 for e in dummy_embeddings)
    assert all(e.vector is not None and len(e.vector) > 0 for e in dummy2_embeddings)


def test_list_models():
    """Test that list_models returns a list of available embedding models."""

    # Call the list_models function
    available_models = list_models()

    # Check that it returns a list
    assert isinstance(available_models, list)

    # Check that the list is not empty
    assert len(available_models) > 0

    # Check that it contains the expected models we've tested
    expected_models = [
        "Dummy",
        "Dummy2",
        "NomicText",
        "NomicVision",
        "Nomic",
        "JinaClip",
    ]
    for model in expected_models:
        assert model in available_models

    # Verify the base class is not included
    assert "EmbeddingModel" not in available_models
