"""Model training and evaluation for flood risk prediction.

Trains a RandomForest classifier on engineered features,
evaluates on held-out test set, and saves artifacts.
"""

import json
import logging
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split

from .config import settings
from .data import load_and_validate
from .features import add_spatial_features, engineer_features

logger = logging.getLogger(__name__)


def train_model(
    features_df: pd.DataFrame,
    target: pd.Series,
    test_size: float = 0.2,
    random_state: int | None = None,
) -> dict:
    """Train RandomForest classifier for flood risk prediction.

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

    logger.info(f"Training RandomForest with {len(features_df)} samples")

    # Train-test split
    X_train, X_test, y_train, y_test = train_test_split(
        features_df,
        target,
        test_size=test_size,
        random_state=random_state,
        stratify=target,
    )

    logger.info(f"Train: {len(X_train)}, Test: {len(X_test)}")
    logger.info(f"Target distribution (train): {y_train.value_counts().to_dict()}")

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
    y_pred_proba = model.predict_proba(X_test)

    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "f1_weighted": float(f1_score(y_test, y_pred, average="weighted")),
        "f1_macro": float(f1_score(y_test, y_pred, average="macro")),
    }

    # ROC-AUC (one-vs-rest for multiclass)
    try:
        metrics["roc_auc_ovr"] = float(
            roc_auc_score(y_test, y_pred_proba, multi_class="ovr", average="weighted")
        )
    except Exception as e:
        logger.warning(f"Could not compute ROC-AUC: {e}")
        metrics["roc_auc_ovr"] = None

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
        "X_test": X_test,
        "y_test": y_test,
        "y_pred": y_pred,
        "y_pred_proba": y_pred_proba,
        "metrics": metrics,
        "feature_importance": feature_importance,
        "feature_names": list(features_df.columns),
    }


def save_model(
    model_dict: dict,
    model_dir: str | Path | None = None,
) -> Path:
    """Save trained model and metrics to disk.

    Args:
        model_dict: Dictionary from train_model().
        model_dir: Directory to save artifacts. Defaults to settings.models_dir.

    Returns:
        Path to saved model artifact.
    """
    if model_dir is None:
        model_dir = Path(settings.models_dir)
    else:
        model_dir = Path(model_dir)

    model_dir.mkdir(parents=True, exist_ok=True)

    # Save model
    model_path = model_dir / "model.joblib"
    joblib.dump(model_dict["model"], model_path)
    logger.info(f"Saved model to {model_path}")

    # Save metrics
    metrics_path = model_dir / "metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(model_dict["metrics"], f, indent=2)
    logger.info(f"Saved metrics to {metrics_path}")

    # Save feature importance
    importance_path = model_dir / "feature_importance.csv"
    model_dict["feature_importance"].to_csv(importance_path, index=False)
    logger.info(f"Saved feature importance to {importance_path}")

    # Save feature names
    names_path = model_dir / "feature_names.json"
    with open(names_path, "w") as f:
        json.dump(model_dict["feature_names"], f)
    logger.info(f"Saved feature names to {names_path}")

    return model_path


def train_and_save(
    nuts_path: str | Path | None = None,
    flood_path: str | Path | None = None,
    model_dir: str | Path | None = None,
) -> dict:
    """End-to-end training pipeline: load data, engineer features, train, save.

    Args:
        nuts_path: Optional path to NUTS GeoJSON.
        flood_path: Optional path to ISPRA flood data.
        model_dir: Directory to save artifacts.

    Returns:
        Dictionary with trained model and metrics.
    """
    # Load data
    nuts_gdf, flood_gdf = load_and_validate(nuts_path, flood_path)

    # Engineer features
    features_df, target = engineer_features(nuts_gdf, flood_gdf)
    features_df = add_spatial_features(features_df)

    # Train model
    model_dict = train_model(features_df, target)

    # Save
    save_model(model_dict, model_dir)

    return model_dict
