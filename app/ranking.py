from app.models import Bid, Tender

def rank_bids(tender: Tender, bids: list[Bid]) -> list[dict]:
    eligible = [b for b in bids if b.mandatory_met]
    if not eligible:
        return [{"bid_id": b.id, "supplier_id": b.supplier_id, "eligible": False,
                 "score": 0.0, "reason_codes": ["MANDATORY_REQUIREMENTS_NOT_MET"]} for b in bids]

    prices = [b.price for b in eligible]
    deliveries = [b.delivery_days for b in eligible]
    def inverse(value, values):
        lo, hi = min(values), max(values)
        return 100.0 if hi == lo else 100.0 - (value - lo) * 100.0 / (hi - lo)

    results = []
    for b in bids:
        if not b.mandatory_met:
            results.append({"bid_id": b.id, "supplier_id": b.supplier_id, "eligible": False,
                            "score": 0.0, "reason_codes": ["MANDATORY_REQUIREMENTS_NOT_MET"]})
            continue
        p = inverse(b.price, prices)
        d = inverse(b.delivery_days, deliveries)
        trust = 50.0  # V1 baseline; V4 replaces this with verified outcome-based trust
        match = b.requirement_match
        score = (tender.w_price*p + tender.w_delivery*d +
                 tender.w_trust*trust + tender.w_match*match)
        codes = []
        if p >= 70: codes.append("PRICE_COMPETITIVE")
        if d >= 70: codes.append("DELIVERY_FAST")
        if trust >= 50: codes.append("BASELINE_TRUST")
        if match >= 90: codes.append("REQUIREMENT_MATCH_HIGH")
        results.append({"bid_id": b.id, "supplier_id": b.supplier_id, "eligible": True,
                        "price_score": round(p, 2), "delivery_score": round(d, 2),
                        "trust_score": trust, "requirement_match": match,
                        "score": round(score, 2), "reason_codes": codes})
    return sorted(results, key=lambda x: (x["eligible"], x["score"]), reverse=True)
