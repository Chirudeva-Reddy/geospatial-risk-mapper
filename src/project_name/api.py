"""FastAPI inference service."""

from fastapi import FastAPI

from project_name import __version__
from project_name.predict import PredictionRequest, PredictionResponse, predict

app = FastAPI(title="project-name", version=__version__)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/predict", response_model=PredictionResponse)
def predict_endpoint(request: PredictionRequest) -> PredictionResponse:
    return predict(request)
