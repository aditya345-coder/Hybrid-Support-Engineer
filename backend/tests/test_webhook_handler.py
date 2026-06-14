from unittest.mock import patch
from middleware.webhook_handler import handle_push, handle_issue_event, handle_pr_event


def test_handle_push_extracts_md_files():
    payload = {
        "repository": {
            "full_name": "owner/repo",
            "name": "repo",
            "default_branch": "main",
            "owner": {"login": "owner"},
        },
        "commits": [
            {
                "added": ["README.md"],
                "modified": ["docs/guide.md", "src/main.py"],
                "removed": [],
            },
            {
                "added": [],
                "modified": ["docs/api.md"],
                "removed": ["old.md"],
            },
        ],
    }

    with (
        patch("middleware.webhook_handler.VectorStore") as mock_vs,
        patch("middleware.webhook_handler._download_raw_file") as mock_download,
        patch("middleware.webhook_handler._split_markdown") as mock_split,
        patch("middleware.webhook_handler._embed_and_upsert"),
    ):
        mock_download.return_value = "# content"
        mock_split.return_value = [{"text": "# content", "source": "README.md"}]

        handle_push(payload, session_id="test-session")

        # Should have re-indexed 3 .md files (README.md, docs/guide.md, docs/api.md)
        assert mock_download.call_count == 3
        downloaded_files = {call[0][3] for call in mock_download.call_args_list}
        assert downloaded_files == {"README.md", "docs/guide.md", "docs/api.md"}
        # old.md was removed, not added/modified — should NOT be downloaded
        assert "old.md" not in downloaded_files

        # delete_by_metadata should be called for each
        assert mock_vs.return_value.delete_by_metadata.call_count == 3


def test_handle_push_no_md_files():
    payload = {
        "repository": {
            "full_name": "owner/repo",
            "name": "repo",
            "default_branch": "main",
            "owner": {"login": "owner"},
        },
        "commits": [
            {
                "added": ["src/main.py"],
                "modified": ["src/utils.py"],
                "removed": [],
            },
        ],
    }

    with (
        patch("middleware.webhook_handler.VectorStore") as mock_vs,
        patch("middleware.webhook_handler._download_raw_file") as mock_download,
    ):
        handle_push(payload, session_id="test-session")
        mock_download.assert_not_called()
        mock_vs.return_value.delete_by_metadata.assert_not_called()


def test_handle_issue_event_upserts_issue():
    payload = {
        "action": "opened",
        "issue": {
            "number": 123,
            "title": "Bug: CORS not working",
            "body": "When using CORS middleware...\nFeature: middleware",
            "state": "open",
            "html_url": "https://github.com/owner/repo/issues/123",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "user": {"login": "testuser"},
        },
    }

    with patch("middleware.webhook_handler.GraphStore") as mock_gs:
        handle_issue_event(payload, session_id="test-session")

        mock_gs.return_value.upsert_issue.assert_called_once()
        args = mock_gs.return_value.upsert_issue.call_args[0][0]
        assert args["number"] == 123
        assert args["title"] == "Bug: CORS not working"
        assert args["state"] == "open"

        # Should link to middleware feature
        mock_gs.return_value.upsert_issue_affects.assert_called_once_with(
            123, "middleware", session_id="test-session"
        )


def test_handle_issue_event_deleted_skipped():
    payload = {
        "action": "deleted",
        "issue": {"number": 999, "title": "Spam issue"},
    }

    with patch("middleware.webhook_handler.GraphStore") as mock_gs:
        handle_issue_event(payload, session_id="test-session")
        mock_gs.return_value.upsert_issue.assert_not_called()


def test_handle_pr_event_merged():
    payload = {
        "action": "closed",
        "pull_request": {
            "number": 42,
            "title": "Fix CORS bug",
            "body": "Closes #123\nFixes the CORS middleware issue",
            "state": "closed",
            "merged": True,
            "merged_at": "2025-01-02T00:00:00Z",
            "html_url": "https://github.com/owner/repo/pull/42",
            "created_at": "2025-01-01T00:00:00Z",
            "changed_files": 2,
            "files": [
                {"filename": "src/middleware.py"},
                {"filename": "tests/test_middleware.py"},
            ],
        },
    }

    with (
        patch("middleware.webhook_handler.GraphStore") as mock_gs,
        patch("middleware.webhook_handler.requests.get"),
    ):
        handle_pr_event(payload, session_id="test-session")

        mock_gs.return_value.upsert_pr.assert_called_once()
        pr_data = mock_gs.return_value.upsert_pr.call_args[0][0]
        assert pr_data["number"] == 42
        assert pr_data["state"] == "merged"
        assert pr_data["merged"] is True

        mock_gs.return_value.upsert_pr_files.assert_called_once_with(
            42, ["src/middleware.py", "tests/test_middleware.py"], session_id="test-session"
        )


def test_handle_pr_event_not_merged_skipped():
    payload = {
        "action": "closed",
        "pull_request": {
            "number": 99,
            "title": "WIP experiment",
            "body": "Just testing",
            "state": "closed",
            "merged": False,
            "html_url": "",
            "created_at": "",
        },
    }

    with patch("middleware.webhook_handler.GraphStore") as mock_gs:
        handle_pr_event(payload, session_id="test-session")
        mock_gs.return_value.upsert_pr.assert_not_called()
