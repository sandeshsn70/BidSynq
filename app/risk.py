"""Explainable procurement risk signals. Alerts require human review and are not findings of wrongdoing."""
from collections import Counter
from datetime import timezone
import hashlib, json, statistics
from app.audit import canonical_json

def _fingerprint(tender_id, bid_id, rule_key, evidence):
    raw = canonical_json({"tender_id": tender_id, "bid_id": bid_id, "rule_key": rule_key, "evidence": evidence})
    return hashlib.sha256(raw.encode()).hexdigest()

def detect_bid_risks(tender, bids):
    alerts=[]
    if not bids: return alerts
    prices=[float(b.price) for b in bids]
    median=statistics.median(prices)
    deviations=[abs(x-median) for x in prices]
    mad=statistics.median(deviations) if deviations else 0.0
    deadline=tender.deadline if tender.deadline.tzinfo else tender.deadline.replace(tzinfo=timezone.utc)
    # Extreme price deviations use a robust median/MAD rule; very small samples are still flagged cautiously.
    for bid in bids:
        if mad > 0 and abs(float(bid.price)-median)/(1.4826*mad) >= 4.0:
            evidence={"bid_id":bid.id,"price":bid.price,"median_price":median,"robust_deviation":round(abs(float(bid.price)-median)/(1.4826*mad),3)}
            alerts.append({"bid_id":bid.id,"rule_key":"price_outlier_mad","severity":"high","title":"Bid price differs sharply from the bid group",
                           "explanation":"This price is far from the median of bids for this tender. Differences can be legitimate; verify scope, units, taxes and delivery terms.","evidence":evidence})
    counts=Counter(round(float(b.price), 2) for b in bids)
    repeated={price:count for price,count in counts.items() if count >= 3}
    for price,count in repeated.items():
        matching=[b for b in bids if round(float(b.price),2)==price]
        evidence={"rounded_price":price,"bid_count":count,"bid_ids":sorted(b.id for b in matching)}
        alerts.append({"bid_id":None,"rule_key":"repeated_bid_price","severity":"medium","title":"Multiple bids use the same rounded price",
                       "explanation":"Three or more bids share a rounded price. This can occur naturally and is not evidence of collusion; review independently and preserve due process.","evidence":evidence})
    for bid in bids:
        created=bid.created_at
        if created and created.tzinfo is None: created=created.replace(tzinfo=timezone.utc)
        if created and (deadline-created).total_seconds() <= 120 and (deadline-created).total_seconds() >= 0:
            evidence={"bid_id":bid.id,"seconds_before_deadline":max(0,int((deadline-created).total_seconds()))}
            alerts.append({"bid_id":bid.id,"rule_key":"near_deadline_bid","severity":"low","title":"Bid submitted near the deadline",
                           "explanation":"A bid was submitted within two minutes of the deadline. This may be normal bidding behavior; check auction logs and extension rules.","evidence":evidence})
    # Optional unsupervised detector, only when enough bids exist. Its output is another review signal, never a verdict.
    if len(bids) >= 8:
        try:
            import numpy as np
            from sklearn.ensemble import IsolationForest
            matrix=np.array([[float(b.price), float(b.delivery_days), float(b.requirement_match)] for b in bids])
            model=IsolationForest(contamination=0.10, random_state=42)
            labels=model.fit_predict(matrix)
            for bid,label in zip(bids,labels):
                if int(label)==-1:
                    evidence={"bid_id":bid.id,"price":bid.price,"delivery_days":bid.delivery_days,"requirement_match":bid.requirement_match,"detector":"IsolationForest"}
                    alerts.append({"bid_id":bid.id,"rule_key":"multivariate_outlier_iforest","severity":"medium","title":"Bid has an unusual combination of attributes",
                                   "explanation":"An unsupervised model marked this bid as unusual compared with this tender's bids. Model outliers can be valid bids and require human review.","evidence":evidence})
        except Exception:
            pass
    return [{**item,"fingerprint":_fingerprint(tender.id,item.get("bid_id"),item["rule_key"],item["evidence"])} for item in alerts]
