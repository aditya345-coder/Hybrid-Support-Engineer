import ast
import tempfile
from pathlib import Path

import pytest

from ingestion.code_indexer import CodeChunk, CodeIndexer


@pytest.fixture
def sample_py_file():
    content = '''
import os
from typing import Optional

def login(username: str, password: str) -> bool:
    """Authenticate a user with username and password."""
    user = get_user(username)
    if user is None:
        return False
    return verify_password(password, user.password_hash)

def get_user(username: str) -> Optional[dict]:
    """Look up a user by username."""
    return {"username": username, "password_hash": "abc123"}

def verify_password(password: str, hashed: str) -> bool:
    """Check password against hash."""
    return True

class AuthMiddleware:
    """Middleware that validates JWT tokens."""

    def __init__(self, secret_key: str):
        self.secret_key = secret_key

    def authenticate(self, token: str) -> dict:
        """Decode and validate a JWT token."""
        return decode_token(token, self.secret_key)

class RateLimiter:
    """Rate limiting for API endpoints."""

    def __init__(self, max_requests: int = 100):
        self.max_requests = max_requests

    def check_limit(self, user_id: str) -> bool:
        """Check if user is under the rate limit."""
        return True
'''
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        path = f.name
    yield Path(path)
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def empty_py_file():
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write("# just a comment\n")
        path = f.name
    yield Path(path)
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def syntax_error_file():
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write("def broken(\n")
        path = f.name
    yield Path(path)
    Path(path).unlink(missing_ok=True)


class TestCodeIndexer:
    def test_extract_functions(self, sample_py_file):
        indexer = CodeIndexer()
        chunks = indexer.index_file(sample_py_file)
        funcs = [c for c in chunks if c.symbol_type == "function"]
        assert len(funcs) == 3
        names = {f.symbol_name for f in funcs}
        assert names == {"login", "get_user", "verify_password"}

    def test_extract_classes_and_methods(self, sample_py_file):
        indexer = CodeIndexer()
        chunks = indexer.index_file(sample_py_file)
        classes = [c for c in chunks if c.symbol_type == "class"]
        assert len(classes) == 2
        class_names = {c.symbol_name for c in classes}
        assert class_names == {"AuthMiddleware", "RateLimiter"}

        methods = [c for c in chunks if c.symbol_type == "method"]
        assert len(methods) == 4
        method_names = {m.symbol_name for m in methods}
        assert method_names == {"__init__", "authenticate", "__init__", "check_limit"}

    def test_extract_signature_and_docstring(self, sample_py_file):
        indexer = CodeIndexer()
        chunks = indexer.index_file(sample_py_file)
        login = next(c for c in chunks if c.symbol_name == "login")
        assert "username: str" in login.signature
        assert "password: str" in login.signature
        assert "Authenticate a user" in login.docstring

        auth = next(c for c in chunks if c.symbol_name == "authenticate")
        assert "token: str" in auth.signature
        assert "Decode and validate" in auth.docstring

    def test_extract_source_code(self, sample_py_file):
        indexer = CodeIndexer()
        chunks = indexer.index_file(sample_py_file)
        rate_limiter = next(c for c in chunks if c.symbol_name == "RateLimiter")
        assert "max_requests: int = 100" in rate_limiter.source_code
        assert "check_limit" in rate_limiter.source_code

    def test_build_call_graph(self, sample_py_file):
        indexer = CodeIndexer()
        tree = ast.parse(sample_py_file.read_text())
        calls = indexer.build_call_graph(tree)
        assert ("login", "get_user") in calls
        assert ("login", "verify_password") in calls

    def test_empty_file(self, empty_py_file):
        indexer = CodeIndexer()
        chunks = indexer.index_file(empty_py_file)
        assert chunks == []

    def test_syntax_error(self, syntax_error_file):
        indexer = CodeIndexer()
        chunks = indexer.index_file(syntax_error_file)
        assert chunks == []

    def test_line_numbers(self, sample_py_file):
        indexer = CodeIndexer()
        chunks = indexer.index_file(sample_py_file)
        login = next(c for c in chunks if c.symbol_name == "login")
        assert login.line_start >= 1
        assert login.line_end >= login.line_start

    def test_index_directory(self, sample_py_file, empty_py_file):
        indexer = CodeIndexer()
        # Create a temp directory with both files
        tmpdir = sample_py_file.parent
        chunks = indexer.index_directory(tmpdir)
        py_files = indexer.discover_python_files(tmpdir)
        assert len(py_files) >= 2
        assert len(chunks) >= 9  # 3 funcs + 2 classes + 4 methods from sample

    def test_index_directory_excludes_dirs(self, tmp_path):
        indexer = CodeIndexer()
        src = tmp_path / "src"
        src.mkdir()
        (src / "util.py").write_text("def foo(): pass")
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_util.py").write_text("def test_foo(): pass")

        chunks = indexer.index_directory(tmp_path, exclude_dirs=["tests"])
        assert len(chunks) == 1
        assert chunks[0].symbol_name == "foo"

    def test_index_directory_no_exclude(self, tmp_path):
        indexer = CodeIndexer()
        src = tmp_path / "src"
        src.mkdir()
        (src / "util.py").write_text("def foo(): pass")
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_util.py").write_text("def test_foo(): pass")

        chunks = indexer.index_directory(tmp_path)
        assert len(chunks) == 2

    def test_index_directory_skips_syntax_errors(self, tmp_path):
        indexer = CodeIndexer()
        (tmp_path / "good.py").write_text("def foo(): pass")
        (tmp_path / "bad.py").write_text("def broken(")
        chunks = indexer.index_directory(tmp_path)
        assert len(chunks) == 1
        assert chunks[0].symbol_name == "foo"

    def test_discover_python_files_non_existent_dir(self):
        indexer = CodeIndexer()
        files = indexer.discover_python_files(Path("/nonexistent/path"))
        assert files == []

    def test_chunk_dataclass_fields(self):
        chunk = CodeChunk(
            file_path="test.py",
            symbol_name="foo",
            symbol_type="function",
            signature="def foo()",
            docstring="Does foo.",
            source_code="def foo():\n    pass",
            line_start=1,
            line_end=2,
            callers=[],
            callees=[],
        )
        assert chunk.file_path == "test.py"
        assert chunk.symbol_name == "foo"
        assert chunk.symbol_type == "function"
