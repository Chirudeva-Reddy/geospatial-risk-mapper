"""Prediction utilities for flood risk scoring.

Loads trained model and generates predictions on new data.
"""

import json
import logging
from pathlib import Path

import joblib
import pandas as pd
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

RISK_LABELS = {0: "Low", 1: "Medium", 2: "High"}


class PredictionRequest(BaseModel):
    """Request schema for flood risk prediction."""

    flood_area_km2: float = Field(..., ge=0, description="Flood hazard area in km²")
    flood_fraction: float = Field(
        ..., ge=0, le=1, description="Fraction of region covered by flood"
    )
    hazard_p3_fraction: float = Field(
        ..., ge=0, le=1, description="Fraction covered by high-risk (P3) hazard"
    )
    hazard_p2_fraction: float = Field(
        ..., ge=0, le=1, description="Fraction covered by medium-risk (P2) hazard"
    )
    region_area_km2: float = Field(..., ge=0, description="Total region area in km²")


class PredictionResponse(BaseModel):
    """Response schema for flood risk prediction."""

    risk_class: int = Field(
        ...,
        ge=0,
        le=2,
        description="Predicted risk class (0=Low, 1=Medium, 2=High)",
    )
    risk_label: str = Field(..., description="Human-readable risk label")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score")
    probabilities: dict = Field(..., description="Probability per class")


class RiskPredictor:
    """Wrapper for loading and using trained flood risk model."""

    def __init__(self, model_dir: str | Path):
        """Initialize predictor by loading model and metadata.

        Args:
            model_dir: Directory containing model artifacts.

        Raises:
            FileNotFoundError: If model files not found.
        """
        model_dir = Path(model_dir)

        # Load model
        model_path = model_dir / "model.joblib"
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found at {model_path}")
        self.model = joblib.load(model_path)
        logger.info(f"Loaded model from {model_path}")

        # Load feature names
        names_path = model_dir / "feature_names.json"
        if not names_path.exists():
            raise FileNotFoundError(f"Feature names not found at {names_path}")
        with open(names_path) as f:
            self.feature_names = json.load(f)
        logger.info(f"Loaded {len(self.feature_names)} feature names")

    def predict(self, features: dict | pd.Series) -> PredictionResponse:
        """Predict flood risk for given features.

        Args:
            features: Dictionary or Series with feature values.

        Returns:
            PredictionResponse with risk class and confidence.

        Raises:
            ValueError: If features are invalid or missing.
        """
        if isinstance(features, dict):
            features = pd.Series(features)

        # Validate features
        if not all(name in features.index for name in self.feature_names):
            missing = [n for n in self.feature_names if n not in features.index]
            raise ValueError(f"Missing features: {missing}")

        # Reorder features
        X = features[self.feature_names].values.reshape(1, -1)  # type: ignore

        # Predict
        risk_class = int(self.model.predict(X)[0])
        probabilities = self.model.predict_proba(X)[0]
        confidence = float(probabilities[risk_class])

        # Handle case where model has fewer than 3 classes
        prob_dict = {
            "low": float(probabilities[0]) if len(probabilities) > 0 else 0.0,
            "medium": float(probabilities[1]) if len(probabilities) > 1 else 0.0,
            "high": float(probabilities[2]) if len(probabilities) > 2 else 0.0,
        }

        return PredictionResponse(
            risk_class=risk_class,
            risk_label=RISK_LABELS[risk_class],
            confidence=confidence,
            probabilities=prob_dict,
        )

    def predict_batch(
        self,
        features_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Predict flood risk for multiple regions.

        Args:
            features_df: DataFrame with features (index=NUTS_ID).

        Returns:
            DataFrame with predictions and confidence.
        """
        # Reorder features
        X = features_df[self.feature_names]

        # Predict
        risk_classes = self.model.predict(X)
        probabilities = self.model.predict_proba(X)

        # Extract confidence for each prediction
        confidences = []
        for i, risk_class in enumerate(risk_classes):
            if risk_class < len(probabilities[i]):
                confidences.append(float(probabilities[i, risk_class]))
            else:
                confidences.append(0.0)

        results = pd.DataFrame(
            {
                "NUTS_ID": features_df.index,
                "risk_class": risk_classes,
                "risk_label": [RISK_LABELS[c] for c in risk_classes],
                "confidence": confidences,
            }
        )

        return results
