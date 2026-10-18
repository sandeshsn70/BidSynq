# Product specification — BidSynq V2

## Product goal
Give B2B buyers and suppliers one workspace to publish sourcing needs, submit commercial offers, and review procurement options with clear access rules.

## User roles

- **Buyer:** publishes tenders, sees only tenders they own, closes/cancels their open tenders, and views bids after a sealed tender closes.
- **Supplier:** browses open tenders, submits one initial offer per tender, and can view only their own submitted offer.
- **Admin:** can access cross-tenant API views and buyer controls. Admin registration is disabled by default; provision admins through a controlled operator workflow before deployment.

## Tender methods

| Method | V2 behaviour | Current limitation |
|---|---|---|
| RFQ | Buyer requests a quote; supplier submits one bid | No multi-round clarification thread |
| Sealed | Buyer cannot view bids while tender status is `open` | No encrypted bid envelopes or independent opening ceremony |
| Reverse auction | Supplier may revise their own bid downward; last-two-minute activity can extend deadline | No live event stream or automatic winner selection |

## Core business rules

1. Tender deadlines must be in the future at creation time.
2. Evaluation weights must sum to 1.0 within a 0.001 tolerance.
3. Only buyer/admin roles can create tenders. Buyers can only manage their own tenders.
4. Only suppliers can submit bids; a supplier has one initial bid per tender.
5. Initial bid price must be positive; delivery days and validity days must be positive.
6. A reverse-auction revision must be strictly lower than the supplier's previous price.
7. A tender can be closed or cancelled only while it is open.
8. Final ranking is advisory and available only after the tender is no longer open.
9. Sealed bids are not returned to buyer/admin callers while the tender is open.
10. Anti-sniping applies to reverse auctions only and extends the deadline to two minutes from the accepted bid if the bid arrives in the final two minutes.

## V2 acceptance checklist

- [ ] Buyer and supplier can register and sign in.
- [ ] Buyer publishes a tender with a future deadline.
- [ ] Supplier submits an offer to an open tender.
- [ ] A second initial bid from the same supplier/tender is rejected.
- [ ] Supplier cannot read another supplier's bid.
- [ ] Buyer cannot read sealed offers before close.
- [ ] Buyer can close/cancel only their own open tender.
- [ ] Reverse-auction revision rejects a price equal to or above the current price.
- [ ] Final ranking endpoint refuses open tenders.
- [ ] UI displays useful success/error feedback.


## V5 extension
Risk review signals, hash-chained audit events, chain verification and deployment hardening. Risk signals remain advisory and require human review.
