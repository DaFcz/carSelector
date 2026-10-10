import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from app.core import config
from app.core.security_headers import CONTENT_SECURITY_POLICY, SecurityHeadersMiddleware


def test_api_responses_carry_security_headers(client: TestClient) -> None:
    response = client.get("/api/brands")
    assert response.status_code == 200
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert "frame-ancestors 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "SAMEORIGIN"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_error_responses_carry_them_too(client: TestClient) -> None:
    response = client.get("/api/models/999999")
    assert response.status_code == 404
    assert response.headers["x-frame-options"] == "SAMEORIGIN"


def _app() -> TestClient:
    app = FastAPI()

    @app.get("/plain")
    def plain() -> PlainTextResponse:
        return PlainTextResponse("ok")

    @app.get("/framable")
    def framable() -> PlainTextResponse:
        return PlainTextResponse("ok", headers={"X-Frame-Options": "DENY"})

    app.add_middleware(SecurityHeadersMiddleware)
    return TestClient(app)


def test_hsts_only_when_served_over_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "SESSION_COOKIE_HTTPS_ONLY", False)
    assert "strict-transport-security" not in _app().get("/plain").headers
    monkeypatch.setattr(config, "SESSION_COOKIE_HTTPS_ONLY", True)
    assert _app().get("/plain").headers["strict-transport-security"].startswith("max-age=")


def test_a_header_the_route_set_is_kept() -> None:
    response = _app().get("/framable")
    assert response.headers.get_list("x-frame-options") == ["DENY"]
