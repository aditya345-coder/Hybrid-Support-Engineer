from middleware.auth import get_current_user


def test_solve_ticket_off_topic():
    from fastapi.testclient import TestClient
    from main import app

    app.dependency_overrides[get_current_user] = lambda: {"sub": "anonymous", "permissions": []}
    client = TestClient(app)

    response = client.post("/v1/solve-ticket", json={
        "user_query": "How to bake a cake?",
        "session_id": "test-1"
    })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_ingestion"


def test_session_id_presence():
    from fastapi.testclient import TestClient
    from main import app

    app.dependency_overrides[get_current_user] = lambda: {"sub": "anonymous", "permissions": []}
    client = TestClient(app)

    response = client.post("/v1/solve-ticket", json={
        "user_query": "What is this repository about?",
        "session_id": "unique-id-999"
    })
    assert response.json()["metadata"]["session_id"] == "unique-id-999"
