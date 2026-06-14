import pytest
from unittest.mock import MagicMock, patch

from database.graph_store import GraphStore


class MockRecord:
    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        return self._data[key]


class MockResult:
    def __init__(self, records):
        self.records = records

    def __iter__(self):
        return iter(self.records)

    def single(self):
        return self.records[0] if self.records else None


@pytest.fixture
def mock_driver():
    with patch("database.graph_store.GraphDatabase.driver") as mock:
        driver = MagicMock()
        mock.return_value = driver
        yield driver


class TestGraphStoreQueries:
    def test_get_contributors_for_feature(self, mock_driver):
        session_mock = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = session_mock
        session_mock.run.return_value = MockResult([
            MockRecord({"login": "alice", "fixes": 12}),
            MockRecord({"login": "bob", "fixes": 5}),
        ])

        store = GraphStore()
        result = store.get_contributors_for_feature("auth")

        assert len(result) == 2
        assert result[0] == "alice (12 fixes)"
        assert result[1] == "bob (5 fixes)"
        call_query = session_mock.run.call_args[0][0]
        assert "User" in call_query
        assert "Feature" in call_query
        assert "OPENED" in call_query

    def test_get_related_issues_by_text(self, mock_driver):
        session_mock = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = session_mock
        session_mock.run.return_value = MockResult([
            MockRecord({"number": "101", "title": "ConnectionError in auth"}),
            MockRecord({"number": "202", "title": "Fix ConnectionError timeout"}),
        ])

        store = GraphStore()
        result = store.get_related_issues_by_text("ConnectionError")

        assert len(result) == 2
        assert "#101" in result[0]
        assert "#202" in result[1]
        call_query = session_mock.run.call_args[0][0]
        assert "CONTAINS" in call_query

    def test_get_files_changed_for_issue_no_pr(self, mock_driver):
        session_mock = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = session_mock
        session_mock.run.return_value = MockResult([
            MockRecord({"paths": []}),
        ])

        store = GraphStore()
        result = store.get_files_changed_for_issue(123)
        assert result == []

    def test_get_contributors_for_feature_uses_session_id(self, mock_driver):
        session_mock = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = session_mock
        session_mock.run.return_value = MockResult([
            MockRecord({"login": "alice", "fixes": 3}),
        ])

        store = GraphStore()
        result = store.get_contributors_for_feature("auth", session_id="sess_1")

        assert len(result) == 1
        _, kwargs = session_mock.run.call_args
        assert kwargs.get("session_id") == "sess_1"

    def test_get_all_feature_names(self, mock_driver):
        session_mock = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = session_mock
        session_mock.run.return_value = MockResult([
            MockRecord({"name": "auth"}),
            MockRecord({"name": "billing"}),
            MockRecord({"name": "api"}),
        ])

        store = GraphStore()
        result = store.get_all_feature_names()

        assert len(result) == 3
        assert "auth" in result
        assert "billing" in result
        assert "api" in result
        call_query = session_mock.run.call_args[0][0]
        assert "MATCH (n:Feature)" in call_query
        assert "RETURN DISTINCT n.name" in call_query

    def test_get_all_feature_names_with_session_id(self, mock_driver):
        session_mock = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = session_mock
        session_mock.run.return_value = MockResult([
            MockRecord({"name": "auth"}),
        ])

        store = GraphStore()
        result = store.get_all_feature_names(session_id="sess_1")

        assert len(result) == 1
        _, kwargs = session_mock.run.call_args
        assert kwargs.get("session_id") == "sess_1"
        call_query = session_mock.run.call_args[0][0]
        assert "n.session_id" in call_query

    def test_get_all_feature_names_empty(self, mock_driver):
        session_mock = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = session_mock
        session_mock.run.return_value = MockResult([])

        store = GraphStore()
        result = store.get_all_feature_names()
        assert result == []

    def test_ensure_feature(self, mock_driver):
        session_mock = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = session_mock

        store = GraphStore()
        store.ensure_feature("auth")

        call_query = session_mock.run.call_args[0][0]
        _, kwargs = session_mock.run.call_args
        assert "MERGE (f:Feature" in call_query
        assert kwargs.get("feature_name") == "auth"

    def test_ensure_feature_with_session_id(self, mock_driver):
        session_mock = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = session_mock

        store = GraphStore()
        store.ensure_feature("billing", session_id="sess_1")

        _, kwargs = session_mock.run.call_args
        assert kwargs.get("feature_name") == "billing"
        assert kwargs.get("session_id") == "sess_1"
        call_query = session_mock.run.call_args[0][0]
        assert "SET f.session_id" in call_query

    def test_close(self, mock_driver):
        store = GraphStore()
        store.close()
        mock_driver.close.assert_called_once()
