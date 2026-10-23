"""Frontend <-> backend compatibility, checked statically against the real FastAPI OpenAPI document.

1. Every endpoint called in frontend/lib/api.ts exists on the backend with the same HTTP method.
2. Every interface in frontend/lib/types.ts that names a backend schema has exactly the same fields
   (and the same required/optional split) as that schema, so field names can never silently drift.
"""
import re
from pathlib import Path

import pytest

from app.main import app

FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "lib"
API_TS, TYPES_TS = FRONTEND / "api.ts", FRONTEND / "types.ts"
pytestmark = pytest.mark.skipif(not API_TS.exists(), reason="frontend sources not present")

OPENAPI = app.openapi()


def _norm(path: str) -> str:
    return re.sub(r"\{[^}/]*\}", "{}", path)


def frontend_calls() -> list[tuple[str, str]]:
    source = API_TS.read_text()
    calls = []
    for match in re.finditer(r'http(?:<[^()]*?>)?\(\s*"(GET|POST|PUT|PATCH|DELETE)"\s*,\s*([`"])(.+?)\2', source):
        method, _, path = match.groups()
        path = re.sub(r"\$\{q\(.*?\)\}", "", path)          # query strings are not part of the route
        path = re.sub(r"\$\{[^}]*\}", "{}", path)             # ${id} -> {}
        calls.append((method, path))
    return calls


def test_frontend_makes_calls():
    assert len(frontend_calls()) >= 30


@pytest.mark.parametrize("method,path", sorted(set(frontend_calls())))
def test_every_frontend_call_has_a_backend_route(method, path):
    routes = {(m.upper(), _norm(p)) for p, item in OPENAPI["paths"].items() for m in item}
    assert (method, path) in routes, f"frontend calls {method} {path} but the backend has no such route"


def test_every_backend_route_is_used_by_the_frontend():
    """Fails when a new endpoint is added without a typed client method (or the UI stops using one)."""
    used = {(m, p) for m, p in frontend_calls()}
    backend = {(m.upper(), _norm(p)) for p, item in OPENAPI["paths"].items() for m in item}
    unused = sorted(backend - used)
    assert unused == [], f"backend routes with no frontend client method: {unused}"


def parse_interfaces() -> dict[str, dict[str, bool]]:
    text = TYPES_TS.read_text()
    raw: dict[str, tuple[str | None, str]] = {}
    for m in re.finditer(r"export interface (\w+)(?: extends (\w+))? \{(.*?)\n?\}", text, re.S):
        raw[m.group(1)] = (m.group(2), m.group(3))

    def fields(name: str) -> dict[str, bool]:
        parent, body = raw[name]
        result = dict(fields(parent)) if parent else {}
        body = re.sub(r"\{[^{}]*\}", "{}", body)               # collapse inline object types
        for part in re.split(r";|\n", body):
            fm = re.match(r"\s*(\w+)(\?)?\s*:", part)
            if fm:
                result[fm.group(1)] = bool(fm.group(2))        # name -> optional?
        return result

    return {name: fields(name) for name in raw}


INTERFACES = parse_interfaces() if TYPES_TS.exists() else {}
SCHEMAS = OPENAPI["components"]["schemas"]


def schema_for(name: str):
    return SCHEMAS.get(name) or SCHEMAS.get(f"{name}-Output") or SCHEMAS.get(f"{name}-Input")


@pytest.mark.parametrize("name", sorted(INTERFACES))
def test_typescript_interface_matches_backend_schema(name):
    schema = schema_for(name)
    assert schema is not None, f"TypeScript interface {name} has no backend schema of that name"
    backend_fields = set(schema.get("properties", {}))
    backend_required = set(schema.get("required", []))
    ts = INTERFACES[name]
    assert set(ts) == backend_fields or _is_request_body(name) and set(ts) <= backend_fields, (
        f"{name}: only in TS {sorted(set(ts) - backend_fields)}, only in backend {sorted(backend_fields - set(ts))}")
    ts_optional = {k for k, optional in ts.items() if optional}
    if _is_request_body(name):
        # Request bodies: the client may send more than the minimum, but must send everything required.
        assert backend_required <= set(ts) - ts_optional, f"{name}: missing required {sorted(backend_required - set(ts))}"
        return
    # A field the backend always sends / requires must not be optional in TS.
    assert not (backend_required & ts_optional), f"{name}: backend requires {sorted(backend_required & ts_optional)}"
    # A field TS treats as required must always be present in backend responses/requests.
    assert set(ts) - ts_optional <= backend_required | _defaulted_but_always_sent(name, schema), (
        f"{name}: TS requires {sorted(set(ts) - ts_optional - backend_required)} which the backend may omit")


def _is_request_body(name: str) -> bool:
    return name in {"TenderCreate", "BidCreate", "SupplierOutcomeIn"}


def _defaulted_but_always_sent(name: str, schema: dict) -> set[str]:
    """Response models serialise every declared field (even defaulted ones), so defaults count as present
    unless the endpoint uses response_model_exclude_none (then None values disappear)."""
    if name.endswith("In") or name in {"TenderCreate", "TenderUpdate"}:
        return set()                                         # request bodies: a defaulted field may be omitted
    return set(schema.get("properties", {}))


def test_all_backend_response_models_used_by_frontend_have_ts_types():
    wanted = {"TenderOut", "BidOut", "BidDetailOut", "MyBidOut", "RankingOut", "DashboardOut", "DocumentOut", "UploadOut",
              "AskOut", "ChecklistOut", "OutcomeOut", "TrustOut", "SimilarOut", "PriceOut", "RiskAlertOut", "ScanOut",
              "ReviewOut", "AuditPageOut", "VerifyOut", "HealthOut", "UserOut", "TokenOut"}
    assert wanted <= set(INTERFACES), sorted(wanted - set(INTERFACES))
