"""Explainable supplier-trust, tender-similarity, and price-intelligence helpers."""
from __future__ import annotations

import re
from statistics import median
from typing import Any


# Never report a range built from fewer comparable bids than this: with 1-2 samples the
# "range" would simply reveal other suppliers' actual bid prices.
MIN_COMPARABLES = 3


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if result == result and abs(result) != float("inf") else default
    except (TypeError, ValueError, OverflowError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def supplier_trust(outcomes: list[dict]) -> dict:
    """Return an explainable, smoothed 0-100 advisory score from recorded outcomes."""
    valid = [o for o in (outcomes or []) if isinstance(o, dict)]
    n = len(valid)
    prior_score, prior_weight = 70.0, 3.0

    if not n:
        return {
            "score": prior_score,
            "confidence": "no_history",
            "observations": 0,
            "components": {
                "quality": None,
                "on_time_rate": None,
                "issue_rate": None,
            },
            "explanation": (
                "No verified delivery outcomes are recorded. "
                "This is a neutral prior, not a performance judgement."
            ),
        }

    qualities = [
        max(1.0, min(5.0, _number(o.get("quality_score"), 3.0)))
        for o in valid
    ]
    on_time_rate = sum(
        bool(o.get("on_time", False)) for o in valid
    ) / n
    issue_rate = sum(
        max(0, _integer(o.get("issue_count"), 0)) for o in valid
    ) / n
    quality = sum(qualities) / n

    observed = (
        ((quality - 1) / 4 * 100 * 0.55)
        + (on_time_rate * 100 * 0.30)
        + (max(0, 100 - min(issue_rate, 5) * 20) * 0.15)
    )

    score = (
        (observed * n + prior_score * prior_weight)
        / (n + prior_weight)
    )
    confidence = "low" if n < 3 else "medium" if n < 10 else "higher"

    return {
        "score": round(max(0.0, min(100.0, score)), 1),
        "confidence": confidence,
        "observations": n,
        "components": {
            "quality": round(quality, 2),
            "on_time_rate": round(on_time_rate, 3),
            "average_issue_count": round(issue_rate, 2),
        },
        "explanation": (
            "Score combines buyer-recorded quality (55%), on-time delivery "
            "(30%), and issue frequency (15%), smoothed toward a neutral prior. "
            "It is advisory and may reflect reporting bias."
        ),
    }


def token_similarity(a: str, b: str) -> float:
    stop = {
        "the", "and", "for", "with", "from", "supply",
        "procurement", "of", "to", "in", "a", "an", "is", "are",
    }

    ta = {
        t for t in re.findall(r"[a-z0-9]+", str(a or "").lower())
        if len(t) > 2 and t not in stop
    }
    tb = {
        t for t in re.findall(r"[a-z0-9]+", str(b or "").lower())
        if len(t) > 2 and t not in stop
    }

    union = ta | tb
    return len(ta & tb) / len(union) if union else 0.0


def similar_tenders(
    target: dict,
    candidates: list[dict],
    limit: int = 5,
) -> list[dict]:
    target = target or {}
    results = []

    try:
        max_results = max(0, min(int(limit), 50))
    except (TypeError, ValueError):
        max_results = 5

    target_category = str(
        target.get("category") or ""
    ).strip().casefold()
    target_text = (
        f"{target.get('title', '')} "
        f"{target.get('description', '')}"
    )
    target_qty = max(1, _integer(target.get("quantity"), 1))

    for candidate in candidates or []:
        if (
            not isinstance(candidate, dict)
            or candidate.get("id") == target.get("id")
        ):
            continue

        category = str(
            candidate.get("category") or ""
        ).strip().casefold()

        category_match = bool(
            target_category
            and category
            and category == target_category
        )

        text_score = token_similarity(
            target_text,
            f"{candidate.get('title', '')} "
            f"{candidate.get('description', '')}",
        )

        quantity = max(
            1, _integer(candidate.get("quantity"), 1)
        )
        quantity_similarity = (
            min(target_qty, quantity) / max(target_qty, quantity)
        )

        score = (
            (0.55 if category_match else 0.0)
            + (0.35 * text_score)
            + (0.10 * quantity_similarity)
        )

        if category_match or text_score > 0:
            results.append({
                "tender_id": candidate.get("id"),
                "title": candidate.get("title", ""),
                "category": candidate.get("category", ""),
                "quantity": quantity,
                "similarity": round(score, 3),
                "status": candidate.get("status", ""),
                "created_at": candidate.get("created_at"),
            })

    return sorted(
        results,
        key=lambda item: item["similarity"],
        reverse=True,
    )[:max_results]


def estimate_price(target: dict, history: list[dict]) -> dict:
    """Estimate total bid price using an optional ML model or median baseline."""
    target = target or {}
    usable = []

    for item in history or []:
        if not isinstance(item, dict):
            continue

        price = _number(item.get("price"))
        quantity = _integer(item.get("quantity"))

        if price > 0 and quantity > 0:
            usable.append({
                **item,
                "price": price,
                "quantity": quantity,
                "category": str(item.get("category") or "General"),
            })

    target_category = str(target.get("category") or "General")
    target_quantity = max(1, _integer(target.get("quantity"), 1))

    same = [
        item for item in usable
        if item["category"].strip().casefold()
        == target_category.strip().casefold()
    ]

    model_error = "insufficient_training_samples"

    if len(usable) >= 8:
        try:
            import numpy as np
            from sklearn.compose import ColumnTransformer
            from sklearn.preprocessing import OneHotEncoder, StandardScaler
            from sklearn.pipeline import Pipeline
            from sklearn.ensemble import RandomForestRegressor

            x = [
                {
                    "category": item["category"],
                    "quantity": item["quantity"],
                }
                for item in usable
            ]
            y = np.array(
                [item["price"] for item in usable],
                dtype=float,
            )

            try:
                from xgboost import XGBRegressor

                regressor = XGBRegressor(
                    n_estimators=100,
                    max_depth=3,
                    learning_rate=0.05,
                    objective="reg:squarederror",
                    n_jobs=1,
                    random_state=42,
                )
                model_name = "XGBoost"

            except Exception:
                regressor = RandomForestRegressor(
                    n_estimators=120,
                    min_samples_leaf=2,
                    random_state=42,
                    n_jobs=1,
                )
                model_name = "RandomForestRegressor"

            transformer = ColumnTransformer([
                (
                    "category",
                    OneHotEncoder(handle_unknown="ignore"),
                    ["category"],
                ),
                (
                    "quantity",
                    StandardScaler(),
                    ["quantity"],
                ),
            ])

            model = Pipeline([
                ("features", transformer),
                ("model", regressor),
            ])

            model.fit(x, y)

            prediction = float(model.predict([{
                "category": target_category,
                "quantity": target_quantity,
            }])[0])

            if np.isfinite(prediction) and prediction > 0:
                prices = [item["price"] for item in same]

                if len(prices) >= MIN_COMPARABLES:
                    low = float(np.percentile(prices, 20))
                    high = float(np.percentile(prices, 80))
                    source = "model_plus_category_history"
                else:
                    low = prediction * 0.85
                    high = prediction * 1.15
                    source = "model_estimate_only"

                return {
                    "currency": "INR",
                    "predicted_total_price": round(prediction, 2),
                    "suggested_range": {
                        "low": round(max(0, min(low, prediction)), 2),
                        "high": round(max(high, prediction), 2),
                    },
                    "model": model_name,
                    "training_samples": len(usable),
                    "same_category_samples": len(same),
                    "source": source,
                    "explanation": (
                        "Estimate learned from historical bid totals and "
                        "tender quantity/category. The range is indicative, "
                        "not a quote."
                    ),
                    "feature_importance": "Not calculated.",
                }

            model_error = "model_returned_invalid_prediction"

        except Exception as exc:
            model_error = type(exc).__name__

    if len(same) >= MIN_COMPARABLES:
        prices = sorted(item["price"] for item in same)
        center = median(prices)
        low = prices[max(0, int((len(prices) - 1) * 0.2))]
        high = prices[
            min(len(prices) - 1, int((len(prices) - 1) * 0.8))
        ]

        return {
            "currency": "INR",
            "predicted_total_price": round(center, 2),
            "suggested_range": {
                "low": round(min(low, center), 2),
                "high": round(max(high, center), 2),
            },
            "model": "category_median_baseline",
            "training_samples": len(usable),
            "same_category_samples": len(same),
            "source": "historical_comparables",
            "explanation": (
                "A median of same-category historical bid totals is used. "
                "It may be misleading when quantities or specifications differ."
            ),
            "model_note": model_error,
        }

    return {
        "currency": "INR",
        "predicted_total_price": None,
        "suggested_range": None,
        "model": None,
        "training_samples": len(usable),
        "same_category_samples": len(same),
        "source": "insufficient_data",
        "explanation": (
            f"There is not enough comparable historical data (at least {MIN_COMPARABLES} "
            "same-category bids are needed) to estimate a price responsibly."
        ),
        "model_note": model_error,
    }
