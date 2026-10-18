
"""Explainable procurement risk signals.

Alerts are review signals, not findings of wrongdoing.
All alerts require independent human review.
"""
from __future__ import annotations

import hashlib
import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from app.audit import canonical_json


def _number(value: Any, default: float | None = None) -> float | None:
    """Convert a value to a finite float, rejecting invalid numbers."""
    try:
        result = float(value)
        if math.isfinite(result):
            return result
    except (TypeError, ValueError, OverflowError):
        pass
    return default


def _fingerprint(
    tender_id: Any,
    bid_id: Any,
    rule_key: str,
    evidence: dict,
) -> str:
    """Generate a deterministic fingerprint for an alert."""
    raw = canonical_json({
        "tender_id": tender_id,
        "bid_id": bid_id,
        "rule_key": rule_key,
        "evidence": evidence,
    })
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _as_utc(value: Any) -> datetime | None:
    """Convert a datetime to UTC; return None for invalid values."""
    if not isinstance(value, datetime):
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _make_alert(
    bid_id: Any,
    rule_key: str,
    severity: str,
    title: str,
    explanation: str,
    evidence: dict,
) -> dict:
    """Build a consistent alert payload."""
    return {
        "bid_id": bid_id,
        "rule_key": rule_key,
        "severity": severity,
        "title": title,
        "explanation": explanation,
        "evidence": evidence,
    }


def detect_bid_risks(tender, bids):
    """Detect explainable bid anomalies for human review.

    Returns alert dictionaries compatible with the existing backend.
    Invalid numeric values are excluded from numeric comparisons.
    """
    if not tender or not bids:
        return []

    tender_id = getattr(tender, "id", None)
    deadline = _as_utc(getattr(tender, "deadline", None))
    alerts = []

    # Keep only bids with usable prices for price-based checks.
    priced_bids = []
    for bid in bids:
        price = _number(getattr(bid, "price", None))
        if price is not None and price >= 0:
            priced_bids.append((bid, price))

    # 1. Extreme price deviations using median absolute deviation.
    if len(priced_bids) >= 3:
        prices = [price for _, price in priced_bids]
        median_price = statistics.median(prices)
        deviations = [abs(price - median_price) for price in prices]
        mad = statistics.median(deviations)

        if mad > 0:
            for bid, price in priced_bids:
                robust_deviation = (
                    abs(price - median_price) / (1.4826 * mad)
                )

                if robust_deviation >= 4.0:
                    evidence = {
                        "bid_id": bid.id,
                        "price": price,
                        "median_price": median_price,
                        "robust_deviation": round(robust_deviation, 3),
                    }
                    alerts.append(_make_alert(
                        bid.id,
                        "price_outlier_mad",
                        "high",
                        "Bid price differs sharply from the bid group",
                        (
                            "This price is far from the median of bids for "
                            "this tender. Differences can be legitimate; "
                            "verify scope, units, taxes and delivery terms."
                        ),
                        evidence,
                    ))

    # 2. Repeated prices, rounded to two decimal places.
    price_counts = Counter(round(price, 2) for _, price in priced_bids)
    repeated_prices = {
        price: count
        for price, count in price_counts.items()
        if count >= 3
    }

    for price, count in sorted(repeated_prices.items()):
        matching_ids = sorted(
            bid.id
            for bid, bid_price in priced_bids
            if round(bid_price, 2) == price
        )
        evidence = {
            "rounded_price": price,
            "bid_count": count,
            "bid_ids": matching_ids,
        }
        alerts.append(_make_alert(
            None,
            "repeated_bid_price",
            "medium",
            "Multiple bids use the same rounded price",
            (
                "Three or more bids share a rounded price. This can occur "
                "naturally and is not evidence of collusion. Review bids "
                "independently and preserve due process."
            ),
            evidence,
        ))

    # 3. Bids submitted within two minutes of the deadline.
    if deadline is not None:
        for bid in bids:
            created = _as_utc(getattr(bid, "created_at", None))
            if created is None:
                continue

            seconds_remaining = (deadline - created).total_seconds()

            if 0 <= seconds_remaining <= 120:
                evidence = {
                    "bid_id": bid.id,
                    "seconds_before_deadline": int(seconds_remaining),
                }
                alerts.append(_make_alert(
                    bid.id,
                    "near_deadline_bid",
                    "low",
                    "Bid submitted near the deadline",
                    (
                        "A bid was submitted within two minutes of the "
                        "deadline. This may be normal bidding behavior; "
                        "check auction logs and extension rules."
                    ),
                    evidence,
                ))

    # 4. Optional multivariate outlier detection.
    # Run only when enough complete, valid observations are available.
    valid_feature_rows = []

    for bid in bids:
        price = _number(getattr(bid, "price", None))
        delivery_days = _number(getattr(bid, "delivery_days", None))
        requirement_match = _number(
            getattr(bid, "requirement_match", None)
        )

        if (
            price is not None
            and delivery_days is not None
            and requirement_match is not None
            and price >= 0
            and delivery_days >= 0
        ):
            valid_feature_rows.append((
                bid,
                [price, delivery_days, requirement_match],
            ))

    if len(valid_feature_rows) >= 8:
        try:
            import numpy as np
            from sklearn.ensemble import IsolationForest

            matrix = np.asarray(
                [features for _, features in valid_feature_rows],
                dtype=float,
            )

            if np.isfinite(matrix).all():
                model = IsolationForest(
                    contamination=0.10,
                    random_state=42,
                    n_estimators=100,
                )
                labels = model.fit_predict(matrix)

                for (bid, _), label in zip(valid_feature_rows, labels):
                    if int(label) != -1:
                        continue

                    evidence = {
                        "bid_id": bid.id,
                        "price": _number(bid.price),
                        "delivery_days": _number(bid.delivery_days),
                        "requirement_match": _number(
                            bid.requirement_match
                        ),
                        "detector": "IsolationForest",
                    }
                    alerts.append(_make_alert(
                        bid.id,
                        "multivariate_outlier_iforest",
                        "medium",
                        "Bid has an unusual combination of attributes",
                        (
                            "An unsupervised model marked this bid as "
                            "unusual compared with this tender's bids. "
                            "Model outliers can be valid bids and require "
                            "human review."
                        ),
                        evidence,
                    ))
        except (ImportError, ValueError, TypeError, ArithmeticError):
            # Optional analysis must not break the main risk-scan endpoint.
            pass

    # Add deterministic fingerprints without changing the alert contract.
    result = []
    seen = set()

    for alert in alerts:
        fingerprint = _fingerprint(
            tender_id,
            alert.get("bid_id"),
            alert["rule_key"],
            alert["evidence"],
        )

        # Prevent duplicate identical alerts in a single scan.
        if fingerprint in seen:
            continue
        seen.add(fingerprint)

        result.append({
            **alert,
            "fingerprint": fingerprint,
        })

    return result
