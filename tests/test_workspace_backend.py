"""Real FastAPI requests; this is not an actual Desktop host smoke test."""

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.plugin_api import router


def test_backend_catalogue_preview_and_no_privileged_routes():
    app = FastAPI()
    app.include_router(router, prefix="/api/plugins/hermes-minefield")
    with TestClient(app) as client:
        root = "/api/plugins/hermes-minefield"
        assert client.get(root + "/workspace").json()["sharing"] == "OFF"
        assert client.get(root + "/checks").json()["checks"]
        response = client.post(root + "/preview", json={"probe_ids": ["request_validation"]})
        assert response.status_code == 200
        assert response.json()["state"] == "PREVIEW_ONLY"
        assert (
            client.post(
                root + "/preview", json={"probe_ids": ["request_validation"], "approved": True}
            ).status_code
            == 400
        )
        assert client.post(root + "/approve", json={"approved": True}).status_code == 404
