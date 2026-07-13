"""Model training and evaluation for flood risk prediction.

Trains both RandomForest classifier (3-class risk) and regressor (continuous risk score).
"""

import json
import logging
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, mean_squared_error
from sklearn.model_selection import train_test_split

from .config import settings
from .data import load_and_validate
from .features import add_spatial_features, engineer_features

logger = logging.getLogger(__name__)


def train_classifier(
    features_df: pd.DataFrame,
    target: pd.Series,
    test_size: float = 0.2,
    random_state: int | None = None,
) -> dict:
    """Train RandomForest classifier for flood risk classification.

    Predicts 3-class risk: 0=Low, 1=Medium, 2=High.

    Args:
        features_df: DataFrame with engineered features.
        target: Series with target labels (0, 1, 2).
        test_size: Fraction of data for test set.
        random_state: Random seed for reproducibility.

    Returns:
        Dictionary with trained model, metrics, and metadata.
    """
    if random_state is None:
        random_state = settings.random_state

    logger.info(f"Training RandomForest Classifier with {len(features_df)} samples")

    # Train-test split
    X_train, X_test, y_train, y_test = train_test_split(
        features_df,
        target,
        test_size=test_size,
        random_state=random_state,
        stratify=target,
    )

    logger.info(f"Train: {len(X_train)}, Test: {len(X_test)}")
    logger.info(f"Target distribution (train): {y_train.value_counts().to_dict()}")  # type: ignore

    # Train model
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=random_state,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)

    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "f1_weighted": float(f1_score(y_test, y_pred, average="weighted")),
        "f1_macro": float(f1_score(y_test, y_pred, average="macro")),
    }

    logger.info(f"Test metrics: {metrics}")

    # Feature importance
    feature_importance = pd.DataFrame(
        {
            "feature": features_df.columns,
            "importance": model.feature_importances_,
        }
    ).sort_values("importance", ascending=False)

    logger.info(f"Top features:\n{feature_importance.head()}")

    return {
        "model": model,
        "model_type": "classifier",
        "X_test": X_test,
        "y_test": y_test,
        "y_pred": y_pred,
        "metrics": metrics,
        "feature_importance": feature_importance,
        "feature_names": list(features_df.columns),
    }


def train_regressor(
    features_df: pd.DataFrame,
    target_continuous: pd.Series,
    test_size: float = 0.2,
    random_state: int | None = None,
) -> dict:
    """Train RandomForest regressor for continuous flood risk scoring.

    Predicts continuous risk score (0-1) based on flood exposure fraction.

    Args:
        features_df: DataFrame with engineered features.
        target_continuous: Series with continuous target (0-1 flood fraction).
        test_size: Fraction of data for test set.
        random_state: Random seed for reproducibility.

    Returns:
        Dictionary with trained model, metrics, and metadata.
    """
    if random_state is None:
        random_state = settings.random_state

    logger.info(f"Training RandomForest Regressor with {len(features_df)} samples")

    # Train-test split
    X_train, X_test, y_train, y_test = train_test_split(
        features_df,
        target_continuous,
        test_size=test_size,
        random_state=random_state,
    )

    logger.info(f"Train: {len(X_train)}, Test: {len(X_test)}")
    logger.info(f"Target range (train): {y_train.min():.3f} - {y_train.max():.3f}")

    # Train model
    model = RandomForestRegressor(
        n_estimators=100,
        max_depth=10,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=random_state,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)

    mse = mean_squared_error(y_test, y_pred)
    rmse = float(mse ** 0.5)

    metrics = {
        "mae": float(mean_absolute_error(y_test, y_pred)),
        "rmse": rmse,
        "r2": float(model.score(X_test, y_test)),
    }

    logger.info(f"Test metrics: {metrics}")

    # Feature importance
    feature_importance = pd.DataFrame(
        {
            "feature": features_df.columns,
            "importance": model.feature_importances_,
        }
    ).sort_values("importance", ascending=False)

    logger.info(f"Top features:\n{feature_importance.head()}")

    return {
        "model": model,
        "model_type": "regressor",
        "X_test": X_test,
        "y_test": y_test,
        "y_pred": y_pred,
        "metrics": metrics,
        "feature_importance": feature_importance,
        "feature_names": list(features_df.columns),
    }


def save_model(
    model_dict: dict,
    model_dir: str | Path | None = None,
    model_name: str = "model",
) -> Path:
    """Save trained model and metrics to disk.

    Args:
        model_dict: Dictionary from train_classifier() or train_regressor().
        model_dir: Directory to save artifacts. Defaults to settings.models_dir.
        model_name: Name prefix for model files (e.g., 'classifier', 'regressor').

    Returns:
        Path to saved model artifact.
    """
    model_dir = Path(settings.models_dir) if model_dir is None else Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)

    # Save model
    model_path = model_dir / f"{model_name}.joblib"
    joblib.dump(model_dict["model"], model_path)
    logger.info(f"Saved {model_dict['model_type']} to {model_path}")

    # Save metrics
    metrics_path = model_dir / f"{model_name}_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(model_dict["metrics"], f, indent=2)
    logger.info(f"Saved metrics to {metrics_path}")

    # Save feature importance
    importance_path = model_dir / f"{model_name}_feature_importance.csv"
    model_dict["feature_importance"].to_csv(importance_path, index=False)
    logger.info(f"Saved feature importance to {importance_path}")

    # Save feature names
    names_path = model_dir / f"{model_name}_feature_names.json"
    with open(names_path, "w") as f:
        json.dump(model_dict["feature_names"], f)
    logger.info(f"Saved feature names to {names_path}")

    return model_path


def train_and_save_all(
    nuts_path: str | Path | None = None,
    flood_path: str | Path | None = None,
    model_dir: str | Path | None = None,
) -> dict:
    """End-to-end training pipeline: load data, engineer features, train both models.

    Args:
        nuts_path: Optional path to NUTS GeoJSON.
        flood_path: Optional path to ISPRA flood data (required).
        model_dir: Directory to save artifacts.

    Returns:
        Dictionary with both classifier and regressor results.
    """
    print("\n" + "=" * 70)
    print("GEOSPATIAL FLOOD RISK MAPPER - MODEL TRAINING PIPELINE")
    print("=" * 70)

    # Load data
    print("\n[1/5] Loading geospatial data...")
    print("      - Loading NUTS 2 administrative boundaries...")
    print("      - Loading ISPRA flood hazard shapefiles (HPH, MPH, LPH)...")
    print("      - This may take a few minutes for large datasets...")
    nuts_gdf, flood_gdf = load_and_validate(nuts_path, flood_path)
    print(f"      ✓ Loaded {len(nuts_gdf)} regions and {len(flood_gdf)} hazard polygons")

    # Engineer features
    print("\n[2/5] Engineering spatial features...")
    print("      - Performing spatial joins...")
    print("      - Computing flood exposure metrics...")
    features_df, target_class = engineer_features(nuts_gdf, flood_gdf)
    features_df = add_spatial_features(features_df)
    print(f"      ✓ Created {len(features_df.columns)} features for {len(features_df)} regions")

    # Create continuous target from flood_fraction
    target_continuous = features_df["flood_fraction"]

    # Train both models
    print("\n[3/5] Training RandomForest Classifier (3-class risk)...")
    classifier_dict = train_classifier(features_df, target_class)
    print(f"      ✓ Classifier accuracy: {classifier_dict['metrics']['accuracy']:.2%}")

    print("\n[4/5] Training RandomForest Regressor (continuous score)...")
    regressor_dict = train_regressor(features_df, target_continuous)
    print(f"      ✓ Regressor MAE: {regressor_dict['metrics']['mae']:.4f}")

    # Save both
    print("\n[5/5] Saving model artifacts...")
    save_model(classifier_dict, model_dir, "classifier")
    save_model(regressor_dict, model_dir, "regressor")
    print("      ✓ Models saved to models/ directory")

    print("\n" + "=" * 70)
    print("TRAINING COMPLETE")
    print("=" * 70)
    print("\nNext steps:")
    print("  - Launch Streamlit UI: make run-app")
    print("  - Serve FastAPI: make run-api")
    print("=" * 70 + "\n")

    return {
        "classifier": classifier_dict,
        "regressor": regressor_dict,
    }
