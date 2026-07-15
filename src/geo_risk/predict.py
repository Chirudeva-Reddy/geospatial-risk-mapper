"""Prediction utilities for flood risk scoring.

Loads trained models (classifier and regressor) and generates predictions.
"""

import json
import logging
from pathlib import Path

import joblib
import pandas as pd
from pydantic import BaseModel, Field

from .features import add_spatial_features

logger = logging.getLogger(__name__)

RISK_LABELS = {0: "Low", 1: "Medium", 2: "High"}


class PredictionRequest(BaseModel):
    """Request schema for flood risk prediction.

    Only the five base input fields are required. The derived interaction
    features `p3_p2_ratio` and `high_hazard_indicator` are computed
    automatically inside `RiskPredictor` from the P3/P2 fractions.
    """

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


class ClassificationResponse(BaseModel):
    """Response schema for classification prediction."""

    risk_class: int = Field(
        ...,
        ge=0,
        le=2,
        description="Predicted risk class (0=Low, 1=Medium, 2=High)",
    )
    risk_label: str = Field(..., description="Human-readable risk label")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score")
    probabilities: dict = Field(..., description="Probability per class")


class RegressionResponse(BaseModel):
    """Response schema for regression prediction."""

    risk_score: float = Field(..., ge=0, le=1, description="Continuous risk score (0=low, 1=high)")
    risk_label: str = Field(..., description="Risk category based on score")


class RiskPredictor:
    """Wrapper for loading and using trained flood risk models."""

    def __init__(self, model_dir: str | Path):
        """Initialize predictor by loading both classifier and regressor.

        Args:
            model_dir: Directory containing model artifacts.

        Raises:
            FileNotFoundError: If model files not found.
        """
        model_dir = Path(model_dir)

        # Load classifier
        classifier_path = model_dir / "classifier.joblib"
        if not classifier_path.exists():
            raise FileNotFoundError(f"Classifier not found at {classifier_path}")
        self.classifier = joblib.load(classifier_path)
        logger.info(f"Loaded classifier from {classifier_path}")

        # Load regressor
        regressor_path = model_dir / "regressor.joblib"
        if not regressor_path.exists():
            raise FileNotFoundError(f"Regressor not found at {regressor_path}")
        self.regressor = joblib.load(regressor_path)
        logger.info(f"Loaded regressor from {regressor_path}")

        # Load feature names
        names_path = model_dir / "classifier_feature_names.json"
        if not names_path.exists():
            raise FileNotFoundError(f"Feature names not found at {names_path}")
        with open(names_path) as f:
            self.feature_names = json.load(f)
        logger.info(f"Loaded {len(self.feature_names)} feature names")

    def predict_classification(self, features: dict | pd.Series) -> ClassificationResponse:
        """Predict flood risk class (Low/Medium/High).

        Accepts either the full feature set or the five base input fields
        (`flood_area_km2`, `flood_fraction`, `hazard_p3_fraction`,
        `hazard_p2_fraction`, `region_area_km2`). Missing derived features
        (`p3_p2_ratio`, `high_hazard_indicator`) are computed automatically.

        Args:
            features: Dictionary or Series with feature values.

        Returns:
            ClassificationResponse with risk class and confidence.

        Raises:
            ValueError: If features are invalid or missing.
        """
        if isinstance(features, dict):
            features = pd.Series(features)
        features = features.copy()

        # Compute derived features if the caller only supplied base inputs.
        if all(
            name in features.index for name in ("hazard_p3_fraction", "hazard_p2_fraction")
        ) and not all(name in features.index for name in self.feature_names):
            features = add_spatial_features(pd.DataFrame([features])).iloc[0]

        # Validate features
        if not all(name in features.index for name in self.feature_names):
            missing = [n for n in self.feature_names if n not in features.index]
            raise ValueError(f"Missing features: {missing}")

        # Reorder features
        X = features[self.feature_names].values.reshape(1, -1)  # type: ignore

        # Predict
        risk_class = int(self.classifier.predict(X)[0])
        probabilities = self.classifier.predict_proba(X)[0]
        confidence = float(probabilities[risk_class])

        # Handle case where model has fewer than 3 classes
        prob_dict = {
            "low": float(probabilities[0]) if len(probabilities) > 0 else 0.0,
            "medium": float(probabilities[1]) if len(probabilities) > 1 else 0.0,
            "high": float(probabilities[2]) if len(probabilities) > 2 else 0.0,
        }

        return ClassificationResponse(
            risk_class=risk_class,
            risk_label=RISK_LABELS[risk_class],
            confidence=confidence,
            probabilities=prob_dict,
        )

    def predict_regression(self, features: dict | pd.Series) -> RegressionResponse:
        """Predict continuous flood risk score (0-1).

        Accepts either the full feature set or the five base input fields
        (`flood_area_km2`, `flood_fraction`, `hazard_p3_fraction`,
        `hazard_p2_fraction`, `region_area_km2`). Missing derived features
        (`p3_p2_ratio`, `high_hazard_indicator`) are computed automatically.

        Args:
            features: Dictionary or Series with feature values.

        Returns:
            RegressionResponse with continuous risk score.

        Raises:
            ValueError: If features are invalid or missing.
        """
        if isinstance(features, dict):
            features = pd.Series(features)
        features = features.copy()

        # Compute derived features if the caller only supplied base inputs.
        if all(
            name in features.index for name in ("hazard_p3_fraction", "hazard_p2_fraction")
        ) and not all(name in features.index for name in self.feature_names):
            features = add_spatial_features(pd.DataFrame([features])).iloc[0]

        # Validate features
        if not all(name in features.index for name in self.feature_names):
            missing = [n for n in self.feature_names if n not in features.index]
            raise ValueError(f"Missing features: {missing}")

        # Reorder features
        X = features[self.feature_names].values.reshape(1, -1)  # type: ignore

        # Predict
        risk_score = float(self.regressor.predict(X)[0])
        risk_score = max(0.0, min(1.0, risk_score))  # Clamp to [0, 1]

        # Assign label based on score
        if risk_score < 0.33:
            risk_label = "Low"
        elif risk_score < 0.67:
            risk_label = "Medium"
        else:
            risk_label = "High"

        return RegressionResponse(
            risk_score=risk_score,
            risk_label=risk_label,
        )

    def predict_batch_classification(
        self,
        features_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Predict flood risk class for multiple regions.

        Args:
            features_df: DataFrame with features (index=NUTS_ID).

        Returns:
            DataFrame with predictions and confidence.
        """
        # Reorder features
        X = features_df[self.feature_names]

        # Predict
        risk_classes = self.classifier.predict(X)
        probabilities = self.classifier.predict_proba(X)

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

    def predict_batch_regression(
        self,
        features_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Predict continuous flood risk score for multiple regions.

        Args:
            features_df: DataFrame with features (index=NUTS_ID).

        Returns:
            DataFrame with continuous risk scores.
        """
        # Reorder features
        X = features_df[self.feature_names]

        # Predict
        risk_scores = self.regressor.predict(X)
        risk_scores = [max(0.0, min(1.0, s)) for s in risk_scores]  # Clamp to [0, 1]

        # Assign labels
        risk_labels = []
        for score in risk_scores:
            if score < 0.33:
                risk_labels.append("Low")
            elif score < 0.67:
                risk_labels.append("Medium")
            else:
                risk_labels.append("High")

        results = pd.DataFrame(
            {
                "NUTS_ID": features_df.index,
                "risk_score": risk_scores,
                "risk_label": risk_labels,
            }
        )

        return results
