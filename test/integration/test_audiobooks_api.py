import uuid
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from routes.audiobooks import router
from fastapi import FastAPI

app = FastAPI()
app.include_router(router, prefix="/audiobooks")

client = TestClient(app)


@pytest.fixture
def mock_service(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("routes.audiobooks._service", lambda: mock)
    return mock


def test_list_playlists(mock_service):
    mock_service.list_playlists.return_value = [{"id": "pl-1", "title": "Test"}]
    mock_service.count_playlists.return_value = 1

    response = client.get("/audiobooks/playlists")
    assert response.status_code == 200
    assert response.json() == {"data": [{"id": "pl-1", "title": "Test"}], "total": 1}

    mock_service.list_playlists.assert_called_once_with(
        status=None, playlist_type=None, limit=50, offset=0
    )


def test_list_playlists_with_filters(mock_service):
    mock_service.list_playlists.return_value = []
    mock_service.count_playlists.return_value = 0

    response = client.get(
        "/audiobooks/playlists?status=published&playlist_type=series&limit=10&offset=5"
    )
    assert response.status_code == 200

    mock_service.list_playlists.assert_called_once_with(
        status="published", playlist_type="series", limit=10, offset=5
    )


def test_get_playlist_not_found(mock_service):
    mock_service.get_playlist_by_slug.return_value = None
    response = client.get("/audiobooks/playlists/non-existent")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_playlist_success_and_masking(mock_service):
    mock_service.get_playlist_by_slug.return_value = {
        "slug": "test-slug",
        "episodes": [
            {"id": "ep-1", "status": "completed", "audio_url": "http://example.com/audio1.mp3"},
            {"id": "ep-2", "status": "generating", "audio_url": "http://example.com/audio2.mp3"},
            {"id": "ep-3", "status": "failed", "audio_url": "http://example.com/audio3.mp3"},
            {"id": "ep-4", "audio_url": "http://example.com/audio4.mp3"},  # missing status
        ],
    }

    response = client.get("/audiobooks/playlists/test-slug")
    assert response.status_code == 200

    data = response.json()["data"]
    episodes = data["episodes"]
    assert episodes[0]["audio_url"] == "http://example.com/audio1.mp3"
    assert episodes[1]["audio_url"] is None
    assert episodes[2]["audio_url"] is None
    assert episodes[3]["audio_url"] is None


def test_get_episode_not_found(mock_service):
    mock_service.get_episode_by_id.return_value = None
    ep_id = uuid.uuid4()
    response = client.get(f"/audiobooks/episodes/{ep_id}")
    assert response.status_code == 404


def test_get_episode_success(mock_service):
    ep_id = str(uuid.uuid4())
    mock_service.get_episode_by_id.return_value = {"id": ep_id, "title": "Test Ep"}

    response = client.get(f"/audiobooks/episodes/{ep_id}")
    assert response.status_code == 200
    assert response.json()["data"]["id"] == ep_id
