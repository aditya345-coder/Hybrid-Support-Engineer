from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CodeChunk:
    file_path: str
    symbol_name: str
    symbol_type: str
    signature: str
    docstring: str
    source_code: str
    line_start: int
    line_end: int
    callers: list[str] = field(default_factory=list)
    callees: list[str] = field(default_factory=list)


class CodeIndexer:
    def discover_python_files(self, directory: Path) -> list[Path]:
        if not directory.is_dir():
            return []
        return sorted(directory.rglob("*.py"))

    def index_directory(
        self,
        directory: Path,
        exclude_dirs: list[str] | None = None,
    ) -> list[CodeChunk]:
        exclude = set(exclude_dirs or [])
        chunks: list[CodeChunk] = []

        for path in self.discover_python_files(directory):
            rel = path.relative_to(directory)
            if any(part in exclude for part in rel.parts):
                continue
            try:
                chunks.extend(self.index_file(path))
            except (SyntaxError, OSError):
                continue

        return chunks

    def index_file(self, path: Path) -> list[CodeChunk]:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return []
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []

        rel_path = str(path)
        chunks: list[CodeChunk] = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                is_async = isinstance(node, ast.AsyncFunctionDef)
                chunk = self._extract_function(node, rel_path, text, is_async=is_async)
                chunks.append(chunk)
            elif isinstance(node, ast.ClassDef):
                class_chunk = self._extract_class(node, rel_path, text)
                chunks.append(class_chunk)
                for item in ast.iter_child_nodes(node):
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_chunk = self._extract_method(
                            item, rel_path, text, node.name
                        )
                        chunks.append(method_chunk)

        return chunks

    def _extract_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, file_path: str, text: str, is_async: bool = False
    ) -> CodeChunk:
        prefix = "async " if is_async else ""
        signature = self._render_signature(node, prefix)
        docstring = ast.get_docstring(node) or ""
        source_code = self._get_source(text, node.lineno, node.end_lineno or node.lineno)
        return CodeChunk(
            file_path=file_path,
            symbol_name=node.name,
            symbol_type="function",
            signature=signature,
            docstring=docstring,
            source_code=source_code,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            callers=[],
            callees=[],
        )

    def _extract_class(
        self, node: ast.ClassDef, file_path: str, text: str
    ) -> CodeChunk:
        bases = ", ".join(
            self._render_expr(b) for b in node.bases if isinstance(b, ast.AST)
        )
        if bases:
            signature = f"class {node.name}({bases})"
        else:
            signature = f"class {node.name}"
        docstring = ast.get_docstring(node) or ""
        source_code = self._get_source(text, node.lineno, node.end_lineno or node.lineno)
        return CodeChunk(
            file_path=file_path,
            symbol_name=node.name,
            symbol_type="class",
            signature=signature,
            docstring=docstring,
            source_code=source_code,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            callers=[],
            callees=[],
        )

    def _extract_method(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: str,
        text: str,
        class_name: str,
    ) -> CodeChunk:
        is_async = isinstance(node, ast.AsyncFunctionDef)
        prefix = "async " if is_async else ""
        signature = self._render_signature(node, prefix)
        docstring = ast.get_docstring(node) or ""
        source_code = self._get_source(text, node.lineno, node.end_lineno or node.lineno)
        return CodeChunk(
            file_path=file_path,
            symbol_name=node.name,
            symbol_type="method",
            signature=signature,
            docstring=docstring,
            source_code=source_code,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            callers=[],
            callees=[],
        )

    def _render_signature(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, prefix: str = ""
    ) -> str:
        args = node.args
        parts: list[str] = []
        # Positional args
        for arg in args.args:
            parts.append(self._render_arg(arg))
        # *args
        if args.vararg:
            parts.append(f"*{args.vararg.arg}")
        # Keyword-only args
        for arg in args.kwonlyargs:
            parts.append(self._render_arg(arg))
        # **kwargs
        if args.kwarg:
            parts.append(f"**{args.kwarg.arg}")

        params = ", ".join(parts)

        returns = ""
        if node.returns:
            returns = f" -> {self._render_expr(node.returns)}"

        return f"{prefix}def {node.name}({params}){returns}"

    def _render_arg(self, arg: ast.arg) -> str:
        if arg.annotation:
            return f"{arg.arg}: {self._render_expr(arg.annotation)}"
        return arg.arg

    def _render_expr(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self._render_expr(node.value)}.{node.attr}"
        if isinstance(node, ast.Subscript):
            value = self._render_expr(node.value)
            sl = self._render_slice(node.slice)
            return f"{value}[{sl}]"
        if isinstance(node, ast.Constant):
            return repr(node.value)
        if isinstance(node, ast.Tuple):
            elts = ", ".join(self._render_expr(e) for e in node.elts)
            return f"[{elts}]"
        return "?"

    def _render_slice(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self._render_expr(node.value)}.{node.attr}"
        if isinstance(node, ast.Subscript):
            value = self._render_expr(node.value)
            sl = self._render_slice(node.slice)
            return f"{value}[{sl}]"
        if isinstance(node, ast.Constant):
            return repr(node.value)
        return "?"

    def _get_source(self, text: str, start: int, end: int) -> str:
        lines = text.splitlines()
        return "\n".join(lines[start - 1 : end])

    def build_call_graph(self, tree: ast.AST) -> list[tuple[str, str]]:
        calls: list[tuple[str, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                caller = node.name
                for child in ast.walk(node):
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                        if child.func.id != caller:
                            calls.append((caller, child.func.id))
        return calls

    def extract_function_info(self, node: ast.FunctionDef) -> dict:
        signature = self._render_signature(node)
        docstring = ast.get_docstring(node) or ""
        callees = [c.func.id for c in ast.walk(node) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)]
        return {
            "name": node.name,
            "signature": signature,
            "docstring": docstring,
            "decorators": [self._render_expr(d) for d in node.decorator_list],
            "line_start": node.lineno,
            "line_end": node.end_lineno or node.lineno,
            "callees": [c for c in callees if c != node.name],
        }

    def extract_class_info(self, node: ast.ClassDef) -> dict:
        bases = [self._render_expr(b) for b in node.bases if isinstance(b, ast.AST)]
        docstring = ast.get_docstring(node) or ""
        return {
            "name": node.name,
            "bases": bases,
            "methods": [
                m.name
                for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
            ],
            "docstring": docstring,
            "line_start": node.lineno,
            "line_end": node.end_lineno or node.lineno,
        }
