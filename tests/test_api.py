from fastapi.testclient import TestClient
import pytest

from zipfit.main import app
from tests.test_rules import CATALOG

client=TestClient(app)


@pytest.fixture(autouse=True)
def stable_catalog(monkeypatch):
    monkeypatch.setattr("zipfit.main.load_catalog", lambda: CATALOG)


def test_full_local_flow_and_document():
    assert client.get("/").status_code==200
    initial=client.get("/api/notices").json()
    assert initial["coverage"]["reviewed_tracks"]==6
    assert all(n["evaluation"]["status"]=="unknown" for n in initial["notices"])
    res=client.post("/api/match",json={"profile":{"birth_date":"1995-04-15","marriage":"single"}})
    assert res.status_code==200
    notice=next(n for n in res.json()["notices"] if n.get("document"))
    pdf=client.get("/api/documents/"+notice["id"])
    assert pdf.status_code==200 and pdf.content.startswith(b"%PDF")
    assert client.get("/api/documents/../../pyproject.toml").status_code==404


def test_invalid_and_cross_origin_inputs():
    assert client.post("/api/match",json={"profile":{"assets_self":-1}}).status_code==422
    assert client.post("/api/match",headers={"Origin":"https://example.com"},json={"profile":{}}).status_code==403
    assert client.get("/api/health",headers={"Host":"example.com"}).status_code==400


def test_response_has_no_profile_persistence_or_cache():
    r=client.post("/api/match",json={"profile":{"assets_self":123}})
    assert r.headers["cache-control"]=="no-store"
    assert "set-cookie" not in r.headers
    assert "profile" not in r.json()
