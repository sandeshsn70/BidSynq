"""Explainable supplier trust and price-intelligence helpers for BidSynq V4."""
from __future__ import annotations
from collections import Counter
from statistics import median
import re

def supplier_trust(outcomes: list[dict]) -> dict:
    """Bayesian-smoothed 0-100 score; no history means neutral prior, not a bad rating."""
    n = len(outcomes)
    prior_score = 70.0
    prior_weight = 3.0
    if not n:
        return {"score": round(prior_score, 1), "confidence": "no_history", "observations": 0,
                "components": {"quality": None, "on_time_rate": None, "issue_rate": None},
                "explanation": "No verified delivery outcomes are recorded. The score is a neutral prior, not a performance judgement."}
    quality = sum(max(1.0, min(5.0, float(o.get("quality_score", 3)))) for o in outcomes) / n
    on_time_rate = sum(bool(o.get("on_time", False)) for o in outcomes) / n
    issue_rate = sum(max(0, int(o.get("issue_count", 0))) for o in outcomes) / n
    observed = (quality - 1) / 4 * 100 * 0.55 + on_time_rate * 100 * 0.30 + max(0, 100 - min(issue_rate, 5) * 20) * 0.15
    score = (observed * n + prior_score * prior_weight) / (n + prior_weight)
    confidence = "low" if n < 3 else "medium" if n < 10 else "higher"
    return {"score": round(max(0, min(100, score)), 1), "confidence": confidence, "observations": n,
            "components": {"quality": round(quality, 2), "on_time_rate": round(on_time_rate, 3), "average_issue_count": round(issue_rate, 2)},
            "explanation": "Score combines buyer-recorded quality (55%), on-time delivery rate (30%) and issue frequency (15%), smoothed toward a neutral prior. It is advisory and may reflect reporting bias."}

def token_similarity(a: str, b: str) -> float:
    stop = {"the", "and", "for", "with", "from", "supply", "procurement", "of", "to", "in"}
    ta = {t for t in re.findall(r"[a-z0-9]+", (a or "").lower()) if len(t) > 2 and t not in stop}
    tb = {t for t in re.findall(r"[a-z0-9]+", (b or "").lower()) if len(t) > 2 and t not in stop}
    return len(ta & tb) / max(1, len(ta | tb))

def similar_tenders(target: dict, candidates: list[dict], limit: int = 5) -> list[dict]:
    results = []
    for c in candidates:
        if c.get("id") == target.get("id"): continue
        category_match = (c.get("category", "").strip().lower() == target.get("category", "").strip().lower())
        text_score = token_similarity(f"{target.get('title','')} {target.get('description','')}", f"{c.get('title','')} {c.get('description','')}")
        qty_a, qty_b = max(1, int(target.get("quantity", 1))), max(1, int(c.get("quantity", 1)))
        qty_similarity = min(qty_a, qty_b) / max(qty_a, qty_b)
        score = (0.55 if category_match else 0.0) + 0.35 * text_score + 0.10 * qty_similarity
        if category_match or text_score > 0:
            results.append({"tender_id": c["id"], "title": c.get("title", ""), "category": c.get("category", ""),
                            "quantity": qty_b, "similarity": round(score, 3), "status": c.get("status", ""),
                            "created_at": c.get("created_at")})
    return sorted(results, key=lambda x: x["similarity"], reverse=True)[:limit]

def estimate_price(target: dict, history: list[dict]) -> dict:
    """Train an optional XGBoost model, else sklearn RF; fall back to same-category historical bids."""
    usable = [h for h in history if float(h.get("price", 0)) > 0 and int(h.get("quantity", 0)) > 0]
    same = [h for h in usable if str(h.get("category", "")).strip().lower() == str(target.get("category", "")).strip().lower()]
    if len(usable) >= 8:
        try:
            import numpy as np
            from sklearn.compose import ColumnTransformer
            from sklearn.preprocessing import OneHotEncoder, StandardScaler
            from sklearn.pipeline import Pipeline
            from sklearn.ensemble import RandomForestRegressor
            X = [{"category": str(h.get("category", "General")), "quantity": int(h["quantity"])} for h in usable]
            y = np.array([float(h["price"]) for h in usable])
            # Prefer XGBoost if installed; a random forest remains a usable local baseline.
            try:
                from xgboost import XGBRegressor
                reg = XGBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05, objective="reg:squarederror", n_jobs=1, random_state=42)
                model_name = "XGBoost"
            except Exception:
                reg = RandomForestRegressor(n_estimators=120, min_samples_leaf=2, random_state=42, n_jobs=1)
                model_name = "RandomForestRegressor"
            pre = ColumnTransformer([("category", OneHotEncoder(handle_unknown="ignore"), ["category"]), ("quantity", StandardScaler(), ["quantity"])])
            model = Pipeline([("features", pre), ("model", reg)])
            model.fit(X, y)
            pred = float(model.predict([{"category": str(target.get("category", "General")), "quantity": int(target.get("quantity", 1))}])[0])
            if pred > 0 and np.isfinite(pred):
                if same:
                    comparable = [float(h["price"]) for h in same]
                    low, high = float(np.percentile(comparable, 20)), float(np.percentile(comparable, 80))
                    source = "model_plus_category_history"
                else:
                    low, high = pred * 0.85, pred * 1.15
                    source = "model_estimate_only"
                return {"currency": "INR", "predicted_total_price": round(pred, 2), "suggested_range": {"low": round(max(0, min(low, pred)), 2), "high": round(max(high, pred), 2)},
                        "model": model_name, "training_samples": len(usable), "same_category_samples": len(same), "source": source,
                        "explanation": "Estimate learned from historical bid totals and tender quantity/category. Range is an indicative uncertainty band, not a quote.",
                        "feature_importance": "Not calculated; install the optional shap package for a future local explanation layer."}
        except Exception as exc:
            model_error = type(exc).__name__
        else:
            model_error = "unknown"
    else:
        model_error = "insufficient_training_samples"
    if same:
        prices = [float(h["price"]) for h in same]
        center = median(prices)
        low = sorted(prices)[max(0, int((len(prices)-1)*0.2))]
        high = sorted(prices)[min(len(prices)-1, int((len(prices)-1)*0.8))]
        return {"currency": "INR", "predicted_total_price": round(center, 2), "suggested_range": {"low": round(min(low, center), 2), "high": round(max(high, center), 2)},
                "model": "category_median_baseline", "training_samples": len(usable), "same_category_samples": len(same), "source": "historical_comparables",
                "explanation": "A simple median of same-category historical bid totals is used because there is not enough history for a reliable ML model. This may be misleading when quantities differ.", "model_note": model_error}
    return {"currency": "INR", "predicted_total_price": None, "suggested_range": None, "model": None, "training_samples": len(usable), "same_category_samples": 0, "source": "insufficient_data",
            "explanation": "Not enough comparable historical bids are available. Collect more completed procurement data before using price estimates.", "model_note": model_error}
