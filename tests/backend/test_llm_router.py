"""Tests for /api/llm/provider runtime switching endpoints."""

import pytest


async def test_get_provider_info(client):
    response = await client.get("/api/llm/provider")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] in ("ollama", "xai", "mock")
    assert body["mode"] in ("live", "mock")
    assert "ollama" in body["available"]
    assert "xai" in body["available"]


async def test_switch_provider_to_xai(client, settings):
    if not settings.xai_api_key:
        pytest.skip("xAI API key not configured in test environment")
    response = await client.post("/api/llm/provider", json={"provider": "xai"})
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "xai"


async def test_switch_provider_invalid(client):
    response = await client.post("/api/llm/provider", json={"provider": "unknown"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PROVIDER"


async def test_switch_provider_persists_in_app_state(client):
    # Default test fixture has no credentials, so switching to xai falls back to mock.
    response = await client.post("/api/llm/provider", json={"provider": "xai"})
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "xai"
    # A subsequent GET reflects the switch.
    get_response = await client.get("/api/llm/provider")
    assert get_response.json()["provider"] == "xai"
