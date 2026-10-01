import asyncio
import json

from fastapi.testclient import TestClient
import pytest

from zipfit.main import create_app
from zipfit.middleware import ProfileBodyLimit
from zipfit.settings import Settings


def test_render_hostname_configuration(monkeypatch):
    monkeypatch.setenv("ZIPFIT_ENV", "production")
    monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", "zipfit-example.onrender.com")
    monkeypatch.setenv("ZIPFIT_ALLOWED_HOSTS", "housing.example.com")
    settings = Settings.from_env()
    assert settings.production
    assert "zipfit-example.onrender.com" in settings.allowed_hosts
    assert "housing.example.com" in settings.allowed_hosts
    assert "testserver" not in settings.allowed_hosts


@pytest.mark.parametrize("environment", ["production", "preview"])
def test_vercel_deployment_and_stable_domains(monkeypatch, environment):
    monkeypatch.delenv("ZIPFIT_ENV", raising=False)
    monkeypatch.setenv("VERCEL_ENV", environment)
    monkeypatch.setenv("VERCEL_URL", "zipfit-build123-example.vercel.app")
    monkeypatch.setenv("VERCEL_BRANCH_URL", "zipfit-git-main-example.vercel.app")
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "zipfit-example.vercel.app")
    settings = Settings.from_env()
    assert settings.production
    assert "zipfit-build123-example.vercel.app" in settings.allowed_hosts
    assert "zipfit-git-main-example.vercel.app" in settings.allowed_hosts
    assert "zipfit-example.vercel.app" in settings.allowed_hosts
    assert "unrelated-project.vercel.app" not in settings.allowed_hosts


@pytest.mark.parametrize("host", ["", "*", "https://housing.example.com", "housing.example.com:443", "*.onrender.com"])
def test_production_requires_exact_hostname(monkeypatch, host):
    monkeypatch.setenv("ZIPFIT_ENV", "production")
    monkeypatch.delenv("RENDER_EXTERNAL_HOSTNAME", raising=False)
    monkeypatch.setenv("ZIPFIT_ALLOWED_HOSTS", host)
    with pytest.raises(ValueError):
        Settings.from_env()


def test_https_site_and_tls_terminating_proxy_accept_same_origin_only():
    settings = Settings(production=True, allowed_hosts=("housing.example.com",))
    app = create_app(settings)
    # External HTTPS may reach the application through an internal HTTP hop.
    with TestClient(app, base_url="http://housing.example.com") as client:
        response = client.post("/api/match", headers={"Origin":"https://housing.example.com"}, json={"profile":{}})
        assert response.status_code == 200
        assert response.headers["strict-transport-security"] == "max-age=31536000"
        assert response.headers["cache-control"] == "no-store"
        for origin in ("http://housing.example.com", "https://attacker.example", "null"):
            assert client.post("/api/match", headers={"Origin":origin}, json={"profile":{}}).status_code == 403
        assert client.get("/api/health", headers={"Host":"attacker.example"}).status_code == 400
        assert client.get("/static/fonts/PretendardVariable.woff2").status_code == 200
        assert client.get("/openapi.json").status_code == 404


def test_profile_body_size_limit():
    with TestClient(create_app(Settings())) as client:
        response = client.post("/api/match", content=json.dumps({"profile":{"residence":"x"*20_000}}), headers={"Content-Type":"application/json"})
        assert response.status_code == 413


def test_chunked_request_cannot_bypass_profile_limit():
    async def exercise():
        received = []
        async def app(scope, receive, send):
            raise AssertionError("Oversized request reached the application")
        events = iter([{"type":"http.request", "body":b"12345", "more_body":True}, {"type":"http.request", "body":b"67890", "more_body":False}])
        async def receive():
            return next(events)
        async def send(message):
            received.append(message)
        await ProfileBodyLimit(app, max_bytes=8)({"type":"http", "method":"POST", "headers":[]}, receive, send)
        assert received[0]["status"] == 413
    asyncio.run(exercise())


def test_release_catalog_works_without_runtime(monkeypatch):
    from zipfit import catalog
    from zipfit.audit import audit
    from pathlib import Path
    monkeypatch.setattr(catalog, "RUNTIME", Path("absent-test-runtime.json"))
    data = catalog.load_catalog()
    assert len(data["notices"]) >= 396
    assert audit(data)["errors"] == []
