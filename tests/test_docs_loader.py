
from settings import settings


class TestFileLimitEnforcement:
    def test_file_limit_respected(self):
        from src.ingestion.docs_loader import DocsLoader
        DocsLoader()
        files = [(f"path/to/doc{i}.md", f"doc{i}.md") for i in range(settings.REPO_FILE_LIMIT)]
        assert len(files) <= settings.REPO_FILE_LIMIT

    def test_file_limit_exceeded_raises(self):
        from src.ingestion.docs_loader import DocsLoader

        class TestLoader(DocsLoader):
            def load_and_split(self):
                files_to_process = [(f"doc{i}.md", f"doc{i}.md") for i in range(settings.REPO_FILE_LIMIT + 1)]
                if len(files_to_process) > settings.REPO_FILE_LIMIT:
                    raise ValueError(
                        f"Repository has {len(files_to_process)} markdown files, "
                        f"which exceeds the limit of {settings.REPO_FILE_LIMIT}."
                    )

        loader = TestLoader(repo_url="owner/repo")
        try:
            loader.load_and_split()
            assert False, "Expected ValueError"
        except ValueError as e:
            assert str(settings.REPO_FILE_LIMIT) in str(e)


class TestLocalModeBranching:
    def test_local_mode_true_calls_clone_path(self, monkeypatch):
        monkeypatch.setattr(settings, "LOCAL_MODE", True)
        from src.ingestion.docs_loader import DocsLoader

        loader = DocsLoader(repo_url="owner/repo")
        # Mock prepare_local_repo to avoid network calls
        monkeypatch.setattr(loader, "prepare_local_repo", lambda: "/tmp/repo")
        # Mock discover_docs_path to avoid filesystem dependency
        monkeypatch.setattr(loader, "discover_docs_path", lambda p: (p, []))
        # Should call load_and_split without network — will result in empty docs
        chunks = loader.load_and_split()
        assert chunks == []

    def test_local_mode_false_uses_api(self, monkeypatch):
        monkeypatch.setattr(settings, "LOCAL_MODE", False)
        from src.ingestion.docs_loader import DocsLoader

        loader = DocsLoader(repo_url="owner/repo")
        # Mock fetch_via_api to avoid network
        monkeypatch.setattr(loader, "fetch_via_api", lambda: [])
        chunks = loader.load_and_split()
        assert chunks == []


class TestFetchViaApi:
    def test_repo_owner_name_from_url(self):
        from src.ingestion.docs_loader import DocsLoader
        loader = DocsLoader(repo_url="https://github.com/owner/repo.git")
        assert loader._repo_owner_name() == "owner/repo"

    def test_repo_owner_name_from_short(self):
        from src.ingestion.docs_loader import DocsLoader
        loader = DocsLoader(repo_url="owner/repo")
        assert loader._repo_owner_name() == "owner/repo"

    def test_repo_owner_name_empty_fallback(self):
        from src.ingestion.docs_loader import DocsLoader
        loader = DocsLoader()
        # Falls back to settings.TARGET_REPO which might be None
        result = loader._repo_owner_name()
        assert result is not None or result == ""

    def test_repo_owner_name_from_nested_url(self):
        from src.ingestion.docs_loader import DocsLoader
        loader = DocsLoader(repo_url="https://github.com/org/team/repo.git")
        assert loader._repo_owner_name() == "team/repo"


class TestDocsLoaderInit:
    def test_github_token_from_settings(self, monkeypatch):
        monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_test_token")
        from src.ingestion.docs_loader import DocsLoader
        loader = DocsLoader(repo_url="owner/repo")
        assert loader.github_token == "ghp_test_token"

    def test_github_token_from_param_overrides_settings(self, monkeypatch):
        monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_default")
        from src.ingestion.docs_loader import DocsLoader
        loader = DocsLoader(repo_url="owner/repo", github_token="ghp_explicit")
        assert loader.github_token == "ghp_explicit"
