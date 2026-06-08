from pathlib import Path

from settings import settings


def test_settings_loads_defaults():
    assert hasattr(settings, "LOCAL_MODE")
    assert hasattr(settings, "REPO_FILE_LIMIT")
    assert hasattr(settings, "RATE_LIMIT_MAX")
    assert hasattr(settings, "AST_ENABLED")


def test_settings_default_values():
    assert settings.REPO_FILE_LIMIT == 500
    assert settings.RATE_LIMIT_MAX == 50
    assert settings.MAX_ISSUES_FETCHED == 20
    assert settings.MAX_VERIFY_RETRIES == 3
    assert settings.DOCS_UPSERT_BATCH == 64
    assert settings.LOCAL_MODE is False


def test_settings_paths():
    assert isinstance(settings.PROJECT_ROOT, Path)
    assert settings.DATA_DIR == settings.PROJECT_ROOT / "data"
    assert settings.RAW_DOCS_DIR == settings.DATA_DIR / "raw_docs"


def test_settings_override_via_monkeypatch(monkeypatch):
    monkeypatch.setattr(settings, "REPO_FILE_LIMIT", 100)
    assert settings.REPO_FILE_LIMIT == 100
    monkeypatch.setattr(settings, "RATE_LIMIT_MAX", 10)
    assert settings.RATE_LIMIT_MAX == 10


def test_settings_ast_exclude_dirs_default():
    assert "tests" in settings.AST_EXCLUDE_DIRS
    assert "node_modules" in settings.AST_EXCLUDE_DIRS
    assert "__pycache__" in settings.AST_EXCLUDE_DIRS
