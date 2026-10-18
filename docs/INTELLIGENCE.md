# V4 Supplier and Price Intelligence

## Supplier trust signals

Buyer/admins may record one post-close outcome per supplier and tender through `POST /tenders/{tender_id}/supplier-outcomes`. The supplier must have submitted a bid. Inputs include buyer-assessed quality (1–5), on-time delivery, issue count and notes. The trust score combines quality (55%), on-time rate (30%) and issue frequency (15%), smoothed toward a neutral prior of 70 with weight 3. No history is explicitly shown as `no_history`, not treated as a negative result. The score is advisory and can reflect buyer reporting bias.

## Similar tenders

`GET /tenders/{id}/similar` uses category equality, token overlap across title/description, and quantity similarity. It is a transparent lexical baseline, not vector semantic search. Only closed/awarded tenders are candidates.

## Fair-price estimate

`GET /tenders/{id}/price-intelligence` uses historical bid totals from closed/awarded tenders. With at least eight valid historical bids it attempts XGBoost if installed, otherwise a scikit-learn random forest. With less data it uses a same-category median baseline where possible; without comparable history it returns no estimate. The displayed range is indicative and must be reviewed by a human. The baseline does not yet perform a full time-aware train/test evaluation and should not be represented as validated production forecasting.

## Explanation and limitations

API responses include source, sample counts, model name and a plain-language explanation. A robust SHAP value report and time/category-aware MAE/MAPE evaluation are planned, not claimed as complete. The current feature set is category and quantity; real-world prices also depend on currency, taxes, delivery terms, quality, location, specifications and date. Do not use the output for automatic award decisions.

## Endpoints

- `POST /tenders/{tender_id}/supplier-outcomes` — buyer/admin, tender must be closed or awarded, supplier must have bid.
- `GET /suppliers/{supplier_id}/trust` — buyers/admins; suppliers can view only their own profile.
- `GET /suppliers/me/trust` — supplier's own profile.
- `GET /tenders/{tender_id}/similar` — authenticated user with tender access.
- `GET /tenders/{tender_id}/price-intelligence` — authenticated user with tender access.
