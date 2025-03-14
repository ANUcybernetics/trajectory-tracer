import numpy as np
import pytest
from PIL import Image

from trajectory_tracer.embeddings import embed


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
    embedding_vector = embed("NomicText", sample_text)

    # Run it again to verify determinism
    embedding_vector2 = embed("NomicText", sample_text)

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
    image = Image.new('RGB', (100, 100), color='red')

    # Get the embedding using the actual model
    embedding_vector = embed("NomicVision", image)

    # Run it again to verify determinism
    embedding_vector2 = embed("NomicVision", image)

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
    image = Image.new('RGB', (100, 100), color='green')
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
    image = Image.new('RGB', (100, 100), color='blue')

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
