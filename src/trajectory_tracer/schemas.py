import io
from datetime import datetime
from enum import Enum
from typing import List, Optional, Union
from uuid import UUID

import numpy as np
from PIL import Image
from pydantic import BaseModel, model_validator
from sqlalchemy import Column, LargeBinary, TypeDecorator
from sqlmodel import JSON, Field, Relationship, SQLModel
from uuid_v7.base import uuid7

## numpy storage helper classes

class NumpyArrayType(TypeDecorator):
    """SQLAlchemy type for storing numpy arrays as binary data."""
    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: Optional[np.ndarray], dialect) -> Optional[bytes]:
        if value is None:
            return None
        return np.asarray(value, dtype=np.float32).tobytes()

    def process_result_value(self, value: Optional[bytes], dialect) -> Optional[np.ndarray]:
        if value is None:
            return None
        return np.frombuffer(value, dtype=np.float32)


class NumpyArrayListType(TypeDecorator):
    """SQLAlchemy type for storing a list of numpy arrays as binary data."""
    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: Optional[List[np.ndarray]], dialect) -> Optional[bytes]:
        if value is None:
            return None

        buffer = io.BytesIO()
        # Save the number of arrays
        num_arrays = len(value)
        buffer.write(np.array([num_arrays], dtype=np.int32).tobytes())

        # For each array, save its shape, dtype, and data
        for arr in value:
            arr_np = np.asarray(arr, dtype=np.float32)  # Ensure it's a numpy array with float32 dtype
            shape = np.array(arr_np.shape, dtype=np.int32)

            # Save shape dimensions
            shape_length = len(shape)
            buffer.write(np.array([shape_length], dtype=np.int32).tobytes())
            buffer.write(shape.tobytes())

            # Save the array data
            buffer.write(arr_np.tobytes())

        return buffer.getvalue()

    def process_result_value(self, value: Optional[bytes], dialect) -> List[np.ndarray]:
        if value is None:
            return []

        buffer = io.BytesIO(value)
        # Read the number of arrays
        num_arrays_bytes = buffer.read(4)  # int32 is 4 bytes
        num_arrays = np.frombuffer(num_arrays_bytes, dtype=np.int32)[0]

        arrays = []
        for _ in range(num_arrays):
            # Read shape information
            shape_length_bytes = buffer.read(4)  # int32 is 4 bytes
            shape_length = np.frombuffer(shape_length_bytes, dtype=np.int32)[0]

            shape_bytes = buffer.read(4 * shape_length)  # Each dimension is an int32 (4 bytes)
            shape = tuple(np.frombuffer(shape_bytes, dtype=np.int32))

            # Calculate number of elements and bytes needed
            n_elements = np.prod(shape)
            n_bytes = n_elements * 4  # float32 is 4 bytes per element

            # Read array data
            array_bytes = buffer.read(n_bytes)
            array_data = np.frombuffer(array_bytes, dtype=np.float32)
            arrays.append(array_data.reshape(shape))

        return arrays


## main DB classes

class InvocationType(str, Enum):
    TEXT = "text"
    IMAGE = "image"


# NOTE: output can't be passed to the constructor, has to be set afterwards (otherwise the setter won't work)
class Invocation(SQLModel, table=True):
    model_config = {"arbitrary_types_allowed": True}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    model: str = Field(..., description="Model class name")
    type: InvocationType
    seed: int
    run_id: UUID = Field(foreign_key="run.id", index=True)
    sequence_number: int = 0
    input_invocation_id: Optional[UUID] = Field(default=None, foreign_key="invocation.id", index=True)
    output_text: Optional[str] = None
    output_image_data: Optional[bytes] = None

    # Relationship attributes
    run: "Run" = Relationship(back_populates="invocations")
    embeddings: List["Embedding"] = Relationship(
        back_populates="invocation",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    input_invocation: Optional["Invocation"] = Relationship(
        sa_relationship_kwargs={"remote_side": "Invocation.id"}
    )

    @property
    def output(self) -> Union[str, Image.Image, None]:
        if self.type == InvocationType.TEXT:
            return self.output_text
        elif self.type == InvocationType.IMAGE and self.output_image_data:
            return Image.open(io.BytesIO(self.output_image_data))
        return None

    @output.setter
    def output(self, value: Union[str, Image.Image, None]) -> None:
        if value is None:
            self.output_text = None
            self.output_image_data = None
        elif isinstance(value, str):
            self.output_text = value
            self.output_image_data = None
        elif isinstance(value, Image.Image):
            self.output_text = None
            buffer = io.BytesIO()
            value.save(buffer, format="WEBP", lossless=True, quality=100)
            self.output_image_data = buffer.getvalue()
        else:
            raise TypeError(f"Expected str, Image, or None, got {type(value)}")

    @property
    def input(self) -> Union[str, Image.Image, None]:
        if self.sequence_number == 0:
            return self.run.initial_prompt
        elif self.input_invocation:
            return self.input_invocation.output
        else:
            return None

    @property
    def duration(self) -> float:
        """Return the duration of the embedding computation in seconds."""
        if self.started_at is None or self.completed_at is None:
            return 0.0
        delta = self.completed_at - self.started_at
        return delta.total_seconds()


class Run(SQLModel, table=True):
    model_config = {"arbitrary_types_allowed": True}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    network: List[str] = Field(default=None, sa_type=JSON)
    seed: int
    length: int
    initial_prompt: str
    invocations: List[Invocation] = Relationship(
        back_populates="run",
        sa_relationship_kwargs={
            "order_by": "Invocation.sequence_number",
            "cascade": "all, delete-orphan"
        }
    )
    persistence_diagrams: List["PersistenceDiagram"] = Relationship(
        back_populates="run",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

    @model_validator(mode='after')
    def validate_fields(self):
        if not self.network:
            raise ValueError("Network list cannot be empty")
        if self.length <= 0:
            raise ValueError("Run length must be greater than 0")
        return self

    @property
    def is_complete(self) -> bool:
        """Check if the run is complete with all invocations and outputs."""
        if not self.invocations:
            return False

        # Check if we have an invocation with the final sequence number
        # (sequence_number is unique, so there will be at most one)
        final_invocation = next((inv for inv in self.invocations if inv.sequence_number == self.length - 1), None)
        if final_invocation is None:
            return False

        # Check that the final invocation has a non-None output
        return final_invocation.output is not None


    @property
    def embeddings(self) -> List["Embedding"]:
        """Get all embeddings for all invocations in this run."""
        result = []
        for invocation in self.invocations:
            result.extend(invocation.embeddings)
        return result


    def embeddings_by_model(self, embedding_model: str) -> List["Embedding"]:
        """
        Get embeddings with a specific model name across all invocations in this run.

        Args:
            embedding_model: Name of the embedding model to filter by

        Returns:
            List of Embedding objects matching the specified model
        """
        result = []
        for invocation in self.invocations:
            # Get embeddings for this invocation that match the model name
            matching_embeddings = [e for e in invocation.embeddings if e.embedding_model == embedding_model]
            result.extend(matching_embeddings)
        return result


class Embedding(SQLModel, table=True):
    model_config = {"arbitrary_types_allowed": True}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)

    invocation_id: UUID = Field(foreign_key="invocation.id", index=True)
    embedding_model: str = Field(..., description="Embedding model class name")
    vector: np.ndarray = Field(default=None, sa_column=Column(NumpyArrayType))

    # Relationship attribute
    invocation: Invocation = Relationship(back_populates="embeddings")

    @property
    def dimension(self) -> int:
        if self.vector is None:
            return 0
        return len(self.vector)

    @property
    def duration(self) -> float:
        """Return the duration of the embedding computation in seconds."""
        if self.started_at is None or self.completed_at is None:
            return 0.0
        delta = self.completed_at - self.started_at
        return delta.total_seconds()


class PersistenceDiagram(SQLModel, table=True):
    model_config = {"arbitrary_types_allowed": True}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)

    generators: List[np.ndarray] = Field(
        default=[],
        sa_column=Column(NumpyArrayListType)
    )

    run_id: UUID = Field(foreign_key="run.id", index=True)
    embedding_model: str = Field(..., description="Embedding model class name")
    run: Run = Relationship(back_populates="persistence_diagrams")

    def get_generators_as_arrays(self) -> List[np.ndarray]:
        """Return generators as numpy arrays."""
        return self.generators  # Already numpy arrays

    @property
    def duration(self) -> float:
        """Return the duration of the embedding computation in seconds."""
        if self.started_at is None or self.completed_at is None:
            return 0.0
        delta = self.completed_at - self.started_at
        return delta.total_seconds()


class ExperimentConfig(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    """Configuration for a trajectory tracer experiment."""
    networks: List[List[str]] = Field(..., description="List of networks (each network is a list of model names)")
    seeds: List[int] = Field(..., description="List of random seeds to use")
    prompts: List[str] = Field(..., description="List of initial text prompts")
    embedding_models: List[str] = Field(..., description="List of embedding model class names")
    run_length: int = Field(..., description="Number of invocations in each run")

    @model_validator(mode='after')
    def validate_fields(self):
        if not self.networks:
            raise ValueError("Networks list cannot be empty")
        if not self.seeds:
            raise ValueError("Seeds list cannot be empty")
        if not self.prompts:
            raise ValueError("Prompts list cannot be empty")
        if not self.embedding_models:
            raise ValueError("embedding_models list cannot be empty")
        if self.run_length <= 0:
            raise ValueError("Run length must be greater than 0")
        return self
