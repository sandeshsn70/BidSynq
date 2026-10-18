"""Transparent, deterministic bid scoring for BidSynq.

The function intentionally returns plain dictionaries because the existing API
serializes these results directly. Scores are decision support, not an automatic
award decision; buyers should review the underlying bid details.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

from app.models import Bid, Tender


def _number(value: Any, default: float = 0.0) -> float:
    """Convert a database value to a finite float without crashing ranking."""
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _inverse_score(value: float, values: list[float]) -> float:
    """Score lower-is-better metrics (price and delivery time) from 0 to 100."""
    if not values:
        return 0.0
    low, high = min(values), max(values)
    if math.isclose(low, high, rel_tol=1e-9, abs_tol=1e-9):
        # Equal bids should receive equal, neutral scores rather than an arbitrary
        # advantage simply because all bidders submitted the same value.
        return 100.0
    return _clamp(100.0 - ((value - low) / (high - low) * 100.0))


def _weight(tender: Tender, name: str) -> float:
    """Read a non-negative scoring weight, tolerating old/null database values."""
    return max(0.0, _number(getattr(tender, name, 0.0)))


def rank_bids(tender: Tender, bids: Iterable[Bid]) -> list[dict[str, Any]]:
    """Rank bids using tender weights and transparent reason codes.

    Mandatory-ineligible bids always score zero. Eligible bids are scored against
    other eligible bids for price and delivery, while trust and requirement-match
    use their stored 0-100 values. Original API response keys are preserved.
    """
    bid_list = list(bids)
    if not bid_list:
        return []

    eligible = [bid for bid in bid_list if bool(getattr(bid, "mandatory_met", False))]
    prices = [_number(getattr(bid, "price", 0.0)) for bid in eligible]
    deliveries = [_number(getattr(bid, "delivery_days", 0.0)) for bid in eligible]

    weights = {
        "price": _weight(tender, "w_price"),
        "delivery": _weight(tender, "w_delivery"),
        "trust": _weight(tender, "w_trust"),
        "match": _weight(tender, "w_match"),
    }
    # If all weights are zero, use an equal-weight fallback so eligible bids can
    # still be compared instead of all appearing to have a meaningful score of 0.
    weight_total = sum(weights.values())
    if weight_total <= 0:
        weights = {key: 1.0 for key in weights}
        weight_total = float(len(weights))

    results: list[dict[str, Any]] = []
    for bid in bid_list:
        bid_id = getattr(bid, "id", None)
        supplier_id = getattr(bid, "supplier_id", None)
        if bid not in eligible:
            results.append({
                "bid_id": bid_id,
                "supplier_id": supplier_id,
                "eligible": False,
                "score": 0.0,
                "reason_codes": ["MANDATORY_REQUIREMENTS_NOT_MET"],
            })
            continue

        price = _number(getattr(bid, "price", 0.0))
        delivery = _number(getattr(bid, "delivery_days", 0.0))
        price_score = _inverse_score(price, prices)
        delivery_score = _inverse_score(delivery, deliveries)
        trust_score = _clamp(_number(getattr(bid, "trust_score", 50.0), 50.0))
        match_score = _clamp(_number(getattr(bid, "requirement_match", 0.0)))

        # Normalize the configured weights, so a set of weights summing to 1,
        # 100, or another positive value produces the same 0-100 score scale.
        score = (
            weights["price"] * price_score
            + weights["delivery"] * delivery_score
            + weights["trust"] * trust_score
            + weights["match"] * match_score
        ) / weight_total

        codes: list[str] = []
        if price_score >= 70:
            codes.append("PRICE_COMPETITIVE")
        if delivery_score >= 70:
            codes.append("DELIVERY_FAST")
        if trust_score >= 50:
            codes.append("BASELINE_TRUST")
        if match_score >= 90:
            codes.append("REQUIREMENT_MATCH_HIGH")
        if not codes:
            codes.append("REVIEW_BID_DETAILS")

        results.append({
            "bid_id": bid_id,
            "supplier_id": supplier_id,
            "eligible": True,
            "price_score": round(price_score, 2),
            "delivery_score": round(delivery_score, 2),
            "trust_score": round(trust_score, 2),
            "requirement_match": round(match_score, 2),
            "score": round(_clamp(score), 2),
            "reason_codes": codes,
        })

    # Eligible bids appear first, highest score first. ID is a deterministic
    # tie-breaker so identical scores do not reorder randomly between requests.
    return sorted(
        results,
        key=lambda row: (
            bool(row["eligible"]),
            _number(row.get("score")),
            -_number(row.get("bid_id"), 0.0),
        ),
        reverse=True,
    )
