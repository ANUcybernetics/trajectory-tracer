import logging
import os
from io import BytesIO

from PIL import Image
from sqlmodel import Session

from trajectory_tracer.schemas import InvocationType, Run

logger = logging.getLogger(__name__)


def export_run_images(run: Run, session: Session, output_dir: str = "image_outputs") -> None:
    """
    Export all image invocations from a run to webp files.

    Args:
        run: The Run object containing invocations
        session: SQLModel Session for database operations
        output_dir: Directory where images will be saved (default: "image_outputs")
    """
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Ensure invocations are loaded
    session.refresh(run)

    # Process each invocation
    for invocation in run.invocations:
        # Skip non-image invocations
        print(invocation.sequence_number, invocation.type)
        if invocation.type != InvocationType.IMAGE:
            continue

        try:
            # Check if output_image_data exists and is not empty
            if not invocation.output_image_data:
                logger.warning(f"No image data found for invocation {invocation.id}")
                continue

            # Create BytesIO object and reset position
            image_data = BytesIO(invocation.output_image_data)
            image_data.seek(0)

            # Load image from output_image_data
            img = Image.open(image_data)

            # Force loading of image data to catch format issues early
            img.load()

            # Get prompt text from invocation's input property
            prompt_text = invocation.input

            # Prepare file path
            file_path = os.path.join(output_dir, f"{invocation.id}.webp")

            # Save image with metadata
            metadata = {
                "prompt": prompt_text,
                "model": invocation.model,
                "sequence_number": str(invocation.sequence_number),
                "seed": str(invocation.seed)
            }

            # Convert to RGB mode for WebP format
            img_with_metadata = img.convert("RGB")
            img_with_metadata.save(file_path, format="WEBP", lossless=True, quality=100)

            logger.info(f"Saved image for invocation {invocation.id} to {file_path}")

        except Exception as e:
            logger.error(f"Error exporting image for invocation {invocation.id}: {e}")
