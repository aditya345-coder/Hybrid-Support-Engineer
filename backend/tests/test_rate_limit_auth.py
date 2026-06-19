from unittest.mock import patch


def test_solve_ticket_uses_user_sub_for_rate_limit():
    """Verify solve_ticket passes user sub to check_rate_limit."""
    from main import app
    from middleware.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {"sub": "auth0|user123", "permissions": []}

    with patch("main.check_rate_limit") as mock_check:
        mock_check.return_value = True
        from fastapi.testclient import TestClient
        client = TestClient(app)
        client.post("/v1/solve-ticket", json={
            "user_query": "How does login work?",
            "session_id": "test-session"
        })
        # check_rate_limit was called — note it may fail later in the chain
        mock_check.assert_called()
        call_args = mock_check.call_args[0]
        assert call_args[0] == "auth0|user123"


def test_solve_ticket_uses_anonymous_when_no_sub():
    """When auth returns no 'sub', fallback to 'anonymous'."""
    from main import app
    from middleware.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {"permissions": []}

    with patch("main.check_rate_limit") as mock_check:
        mock_check.return_value = True
        from fastapi.testclient import TestClient
        client = TestClient(app)
        client.post("/v1/solve-ticket", json={
            "user_query": "How does login work?",
            "session_id": "test-session"
        })
        mock_check.assert_called()
        call_args = mock_check.call_args[0]
        assert call_args[0] == "anonymous"
