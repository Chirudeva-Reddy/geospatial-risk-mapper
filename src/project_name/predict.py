"""Inference logic, imported by api.py / app.py."""

from pydantic import BaseModel


class PredictionRequest(BaseModel):
    # Replace with project-specific input schema.
    pass


class PredictionResponse(BaseModel):
    # Replace with project-specific output schema.
    pass


def predict(request: PredictionRequest) -> PredictionResponse:
    raise NotImplementedError
