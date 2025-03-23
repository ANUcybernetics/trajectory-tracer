import hashlib
import io
import uuid

import ray
from PIL import Image
from sqlmodel import Session

from trajectory_tracer.engine import run_generator
from trajectory_tracer.schemas import (
    Invocation,
    Run,
)


def test_get_output_hash():
    """Test that get_output_hash correctly hashes different types of output."""

    from trajectory_tracer.engine import get_output_hash

    # Test with string output
    text = "Hello, world!"
    text_hash = get_output_hash(text)
    expected_text_hash = hashlib.sha256(text.encode()).hexdigest()
    assert text_hash == expected_text_hash

    # Test with image output
    image = Image.new("RGB", (50, 50), color="blue")
    image_hash = get_output_hash(image)

    # Verify image hash by recreating it
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=30)
    expected_image_hash = hashlib.sha256(buffer.getvalue()).hexdigest()
    assert image_hash == expected_image_hash

    # Test with other type (e.g., integer)
    num = 42

    num_hash = get_output_hash(num)
    expected_num_hash = hashlib.sha256(str(num).encode()).hexdigest()
    assert num_hash == expected_num_hash


def test_run_generator(db_session: Session):
    """Test that run_generator correctly generates a sequence of invocations."""

    # Create a test run
    run = Run(
        network=["DummyT2I", "DummyI2T"],
        initial_prompt="Test prompt",
        seed=42,
        max_length=3,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    # Get the SQLite connection string from the session
    db_url = str(db_session.get_bind().engine.url)

    # Call the generator function with the same DB that db_session is using
    gen_ref = run_generator.remote(str(run.id), db_url)

    # Get the DynamicObjectRefGenerator object
    ref_generator = ray.get(gen_ref)

    # Get the invocation IDs by iterating through the DynamicObjectRefGenerator
    invocation_ids = []
    # Iterate directly over the DynamicObjectRefGenerator
    for invocation_id_ref in ref_generator:
        # Each item is an ObjectRef containing an invocation ID
        invocation_id = ray.get(invocation_id_ref)
        invocation_ids.append(invocation_id)
        if len(invocation_ids) >= 3:
            break

    # Verify we got the expected number of invocations
    assert len(invocation_ids) == 3

    # Verify the invocations are in the database with the right sequence numbers
    for i, invocation_id in enumerate(invocation_ids):
        # Convert string UUID to UUID object if needed
        if isinstance(invocation_id, str):
            invocation_id = uuid.UUID(invocation_id)

        invocation = db_session.get(Invocation, invocation_id)
        assert invocation is not None
        assert invocation.run_id == run.id
        assert invocation.sequence_number == i
