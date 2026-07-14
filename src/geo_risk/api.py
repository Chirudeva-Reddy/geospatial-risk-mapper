"""FastAPI server for flood risk prediction.

Provides REST endpoints for scoring regions by flood risk.
"""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse

from .config import settings
from .predict import (
    PredictionRequest,
    RiskPredictor,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Geospatial Risk Mapper API",
    description="Flood risk prediction for Italian regions",
    version="0.1.0",
)

# Load model on startup
predictor: RiskPredictor | None = None


@app.on_event("startup")
async def startup():
    """Load trained model on startup."""
    global predictor
    try:
        model_dir = Path(settings.models_dir)
        if not model_dir.exists():
            logger.error("Model directory not found")
            return
        predictor = RiskPredictor(model_dir)
        logger.info("Model loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load model: {e}")


@app.get("/")
async def root():
    """Redirect to API documentation."""
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "model_loaded": predictor is not None,
    }


@app.post("/predict/classification")
async def predict_classification(request: PredictionRequest):
    """Predict flood risk class (Low/Medium/High).

    Args:
        request: Features for prediction.

    Returns:
        Classification prediction with risk class and confidence.

    Raises:
        HTTPException: If model not loaded or prediction fails.
    """
    if predictor is None:
        raise HTTPException(
            status_code=503,
            detail="Model not loaded",
        )

    try:
        response = predictor.predict_classification(request.model_dump())
        return response
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Prediction failed: {str(e)}",
        ) from e


@app.post("/predict/regression")
async def predict_regression(request: PredictionRequest):
    """Predict continuous flood risk score (0-1).

    Args:
        request: Features for prediction.

    Returns:
        Regression prediction with continuous risk score.

    Raises:
        HTTPException: If model not loaded or prediction fails.
    """
    if predictor is None:
        raise HTTPException(
            status_code=503,
            detail="Model not loaded",
        )

    try:
        response = predictor.predict_regression(request.model_dump())
        return response
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Prediction failed: {str(e)}",
        ) from e


@app.get("/info")
async def info():
    """Get model information."""
    if predictor is None:
        raise HTTPException(
            status_code=503,
            detail="Model not loaded",
        )

    return {
        "models": {
            "classifier": "RandomForestClassifier (3-class risk)",
            "regressor": "RandomForestRegressor (continuous risk score)",
        },
        "n_features": len(predictor.feature_names),
        "features": predictor.feature_names,
        "risk_classes": {
            0: "Low",
            1: "Medium",
            2: "High",
        },
    }
