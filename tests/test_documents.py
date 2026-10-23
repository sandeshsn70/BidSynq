import io
import zipfile

import pytest

from app.config import settings
from tests.conftest import minimal_docx, minimal_pdf

TXT = b"Bidders must hold ISO 9001 certification. Delivery within 30 days."


def upload(client, actor, tender_id, name, content, ctype="application/octet-stream"):
    return client.post(f"/tenders/{tender_id}/documents", files={"file": (name, content, ctype)}, headers=actor.headers)


def test_upload_txt_docx_pdf_and_list(client, buyer, create_tender):
    t = create_tender()
    r1 = upload(client, buyer, t["id"], "spec.txt", TXT)
    r2 = upload(client, buyer, t["id"], "scope.docx", minimal_docx(["Scope of supply", "Gloves must be cut resistant."]))
    r3 = upload(client, buyer, t["id"], "terms.pdf", minimal_pdf("Payment is due within 45 days of delivery."))
    assert [r.status_code for r in (r1, r2, r3)] == [201, 201, 201], (r1.text, r2.text, r3.text)
    assert r3.json()["chunks_indexed"] >= 1 and r1.json()["file_type"] == "txt"
    docs = client.get(f"/tenders/{t['id']}/documents", headers=buyer.headers).json()
    assert {d["filename"] for d in docs} == {"spec.txt", "scope.docx", "terms.pdf"}
    ans = client.post(f"/tenders/{t['id']}/assistant/ask", json={"question": "When is payment due?"}, headers=buyer.headers).json()
    assert ans["citations"][0]["filename"] == "terms.pdf" and ans["citations"][0]["page_number"] == 1


@pytest.mark.parametrize("name,content,status", [
    ("virus.exe", b"MZ\x90\x00", 415),
    ("notes.md", b"# hi", 415),
    ("noext", b"hello", 415),
    ("empty.txt", b"", 400),
    ("fake.pdf", b"this is plain text pretending to be a pdf", 422),
    ("fake.docx", b"plain text pretending to be docx", 422),
    ("binary.txt", b"abc\x00\x01\x02def", 422),
    ("sneaky.txt", minimal_pdf("hello"), 422),                   # PDF bytes renamed .txt
    ("broken.pdf", b"%PDF-1.4\nthis is not really a pdf", 422),
    ("blank.txt", b"    \n\t  ", 422),
])
def test_upload_rejects_bad_files(client, buyer, create_tender, name, content, status):
    t = create_tender()
    r = upload(client, buyer, t["id"], name, content)
    assert r.status_code == status, r.text
    assert client.get(f"/tenders/{t['id']}/documents", headers=buyer.headers).json() == []   # nothing half-saved


def test_docx_must_contain_word_document_part(client, buyer, create_tender):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("hello.txt", "just a zip")
    assert upload(client, buyer, create_tender()["id"], "x.docx", buf.getvalue()).status_code == 422


def test_size_limit_enforced(client, buyer, create_tender, monkeypatch):
    monkeypatch.setattr(settings, "max_document_mb", 1)
    t = create_tender()
    assert upload(client, buyer, t["id"], "big.txt", b"a " * (1024 * 1024)).status_code == 413
    assert upload(client, buyer, t["id"], "ok.txt", b"a " * 1000).status_code == 201


def test_document_count_limit(client, buyer, create_tender, monkeypatch):
    monkeypatch.setattr(settings, "max_documents_per_tender", 2)
    t = create_tender()
    assert [upload(client, buyer, t["id"], f"{i}.txt", TXT).status_code for i in range(3)] == [201, 201, 409]


def test_path_traversal_filename_is_neutralised(client, buyer, create_tender, tmp_path):
    t = create_tender()
    r = upload(client, buyer, t["id"], "../../../etc/passwd.txt", TXT)
    assert r.status_code == 201 and r.json()["filename"] == "passwd.txt"
    r = upload(client, buyer, t["id"], "..\\..\\windows\\evil.txt", TXT)
    assert r.json()["filename"] == "evil.txt"


def test_stored_files_use_random_names(client, buyer, create_tender, Session):
    from app.models import TenderDocument
    t = create_tender()
    upload(client, buyer, t["id"], "spec.txt", TXT)
    with Session() as s:
        doc = s.query(TenderDocument).one()
    assert doc.stored_filename != "spec.txt" and doc.stored_filename.endswith(".txt") and len(doc.stored_filename) > 30


# ---------------------------------------------------------------------- authorization


def test_only_owner_buyer_or_admin_can_upload_or_delete(client, buyer, buyer2, supplier, admin, create_tender):
    t = create_tender()
    assert upload(client, supplier, t["id"], "a.txt", TXT).status_code == 403
    assert upload(client, buyer2, t["id"], "a.txt", TXT).status_code == 403
    doc = upload(client, admin, t["id"], "a.txt", TXT).json()
    assert client.delete(f"/tenders/{t['id']}/documents/{doc['id']}", headers=buyer2.headers).status_code == 403
    assert client.delete(f"/tenders/{t['id']}/documents/{doc['id']}", headers=supplier.headers).status_code == 403
    assert client.delete(f"/tenders/{t['id']}/documents/{doc['id']}", headers=buyer.headers).json()["status"] == "deleted"
    assert client.get(f"/tenders/{t['id']}/documents", headers=buyer.headers).json() == []
    assert client.delete(f"/tenders/{t['id']}/documents/{doc['id']}", headers=buyer.headers).status_code == 404


def test_other_buyers_cannot_read_or_query_documents(client, buyer, buyer2, create_tender):
    t = create_tender()
    upload(client, buyer, t["id"], "a.txt", TXT)
    assert client.get(f"/tenders/{t['id']}/documents", headers=buyer2.headers).status_code == 403
    q = {"question": "Which certification is needed?"}
    assert client.post(f"/tenders/{t['id']}/assistant/ask", json=q, headers=buyer2.headers).status_code == 403
    assert client.get(f"/tenders/{t['id']}/assistant/requirements", headers=buyer2.headers).status_code == 403


def test_supplier_document_access_rules(client, buyer, supplier, supplier2, create_tender):
    t = create_tender()
    upload(client, buyer, t["id"], "a.txt", TXT)
    q = {"question": "Which certification is needed?"}
    assert len(client.get(f"/tenders/{t['id']}/documents", headers=supplier.headers).json()) == 1       # open tender
    assert client.post(f"/tenders/{t['id']}/assistant/ask", json=q, headers=supplier.headers).status_code == 200
    client.post(f"/tenders/{t['id']}/bids", json={"price": 10, "delivery_days": 3}, headers=supplier.headers)
    client.patch(f"/tenders/{t['id']}/status", json={"status": "closed"}, headers=buyer.headers)
    assert client.get(f"/tenders/{t['id']}/documents", headers=supplier.headers).status_code == 200    # bidder keeps access
    assert client.get(f"/tenders/{t['id']}/documents", headers=supplier2.headers).status_code == 404   # stranger does not
    assert client.post(f"/tenders/{t['id']}/assistant/ask", json=q, headers=supplier2.headers).status_code == 404


def test_unauthenticated_document_access_denied(client, buyer, create_tender):
    t = create_tender()
    assert client.get(f"/tenders/{t['id']}/documents").status_code == 401
    assert client.post(f"/tenders/{t['id']}/documents", files={"file": ("a.txt", TXT)}).status_code == 401


def test_failed_indexing_leaves_no_file_behind(client, buyer, create_tender):
    import os
    folder = settings.document_storage_dir
    before = set(os.listdir(folder)) if os.path.isdir(folder) else set()
    upload(client, buyer, create_tender()["id"], "bad.pdf", b"%PDF-1.4 nope")
    after = set(os.listdir(folder)) if os.path.isdir(folder) else set()
    assert after == before
