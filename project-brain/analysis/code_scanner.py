"""CodeScanner: walks a project directory and extracts a lightweight,
deterministic (regex-based) index of files and symbols (seção 18).

No AST, no execution of project code. Symbol extraction is intentionally
conservative — good enough for SearchAgent/ContextBuilder to locate
candidate files without needing a real PHP/JS parser. Real AST parsing is a
V2 concern (see ARCHITECTURE.md).
"""
from __future__ import annotations

import hashlib
import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path

IGNORED_DIR_NAMES = {
    ".git", "vendor", "node_modules", "storage", "writable", ".vscode",
    ".idea", "__pycache__", "dist", "build", ".venv", "venv",
}
IGNORED_FILE_GLOBS: set[str] = set()

LANGUAGE_BY_EXT = {
    ".php": "php",
    ".js": "javascript",
    ".ts": "typescript",
    ".sql": "sql",
    ".py": "python",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".html": "html",
    ".twig": "twig",
    ".blade.php": "blade",
}

_MAX_FILE_SIZE = 3_000_000  # skip absurdly large files (binaries, dumps)

_PHP_CLASS_RE = re.compile(r"^\s*(?:abstract\s+|final\s+)?class\s+(\w+)", re.MULTILINE)
_PHP_METHOD_RE = re.compile(
    r"^\s*(?:public|protected|private)?\s*(?:static\s+)?function\s+(\w+)\s*\(",
    re.MULTILINE,
)
_PHP_FUNCTION_RE = re.compile(r"^\s*function\s+(\w+)\s*\(", re.MULTILINE)
_CI4_ROUTE_RE = re.compile(
    r"\$routes->(get|post|put|delete|match|resource|group)\s*\(\s*['\"]([^'\"]+)['\"]",
)


@dataclass
class ScannedSymbol:
    symbol_type: str  # class | method | function | route
    name: str
    class_name: str | None
    line_start: int
    line_end: int


@dataclass
class ScannedFile:
    path: str  # relative, posix-style
    absolute_path: Path
    language: str | None
    size: int
    hash: str
    last_modified: str
    symbols: list[ScannedSymbol] = field(default_factory=list)


@dataclass(frozen=True)
class ScanSkip:
    path: str
    reason: str


@dataclass(frozen=True)
class IgnoreMatcher:
    ignored_dirs: frozenset[str]
    ignored_globs: tuple[str, ...]
    sensitive_globs: tuple[str, ...] = ()

    @classmethod
    def default(cls) -> "IgnoreMatcher":
        return cls(
            frozenset(item.casefold() for item in IGNORED_DIR_NAMES),
            tuple(item.replace("\\", "/").casefold() for item in IGNORED_FILE_GLOBS),
            (),
        )

    @classmethod
    def from_config(
        cls,
        ignored_dirs: list[str],
        ignored_globs: list[str],
        sensitive_globs: list[str] | None = None,
    ) -> "IgnoreMatcher":
        return cls(
            frozenset(item.strip("/\\").casefold() for item in ignored_dirs if item.strip("/\\")),
            tuple(
                _strip_relative_prefix(item.replace("\\", "/")).casefold()
                for item in ignored_globs
            ),
            tuple(
                _strip_relative_prefix(item.replace("\\", "/")).casefold()
                for item in (sensitive_globs or [])
            ),
        )

    def reason(self, path: Path | str) -> str | None:
        normalized = _strip_relative_prefix(str(path).replace("\\", "/"))
        parts = tuple(part for part in normalized.split("/") if part)
        for part in parts[:-1]:
            for directory_pattern in self.ignored_dirs:
                if fnmatch.fnmatchcase(part.casefold(), directory_pattern):
                    return f"ignored_dir:{directory_pattern}"
        folded = normalized.casefold()
        basename = parts[-1].casefold() if parts else ""
        for pattern in self.sensitive_globs:
            target = folded if "/" in pattern else basename
            if fnmatch.fnmatchcase(target, pattern) or (
                "/" in pattern and fnmatch.fnmatchcase(folded, f"*/{pattern}")
            ):
                return f"SKIPPED_SENSITIVE:{pattern}"
        for pattern in self.ignored_globs:
            target = folded if "/" in pattern else basename
            if fnmatch.fnmatchcase(target, pattern) or (
                "/" in pattern and fnmatch.fnmatchcase(folded, f"*/{pattern}")
            ):
                return f"ignored_glob:{pattern}"
        return None


def _strip_relative_prefix(value: str) -> str:
    while value.startswith("./"):
        value = value[2:]
    return value


def detect_language(path: Path) -> str | None:
    name = path.name.lower()
    if name.endswith(".blade.php"):
        return "blade"
    return LANGUAGE_BY_EXT.get(path.suffix.lower())


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def extract_php_symbols(text: str) -> list[ScannedSymbol]:
    symbols: list[ScannedSymbol] = []
    class_matches = list(_PHP_CLASS_RE.finditer(text))
    for match in class_matches:
        line = _line_of(text, match.start())
        symbols.append(ScannedSymbol("class", match.group(1), None, line, line))

    def _enclosing_class(pos: int) -> str | None:
        current = None
        for cmatch in class_matches:
            if cmatch.start() <= pos:
                current = cmatch.group(1)
            else:
                break
        return current

    for match in _PHP_METHOD_RE.finditer(text):
        line = _line_of(text, match.start())
        symbols.append(
            ScannedSymbol("method", match.group(1), _enclosing_class(match.start()), line, line)
        )
    for match in _PHP_FUNCTION_RE.finditer(text):
        # Avoid double-counting methods already matched above.
        if any(s.symbol_type == "method" and s.line_start == _line_of(text, match.start()) for s in symbols):
            continue
        line = _line_of(text, match.start())
        symbols.append(ScannedSymbol("function", match.group(1), None, line, line))
    for match in _CI4_ROUTE_RE.finditer(text):
        line = _line_of(text, match.start())
        symbols.append(ScannedSymbol("route", match.group(2), None, line, line))
    return symbols


def should_ignore(path: Path | str, matcher: IgnoreMatcher | None = None) -> bool:
    return (matcher or IgnoreMatcher.default()).reason(path) is not None


def scan_project(
    root: Path,
    matcher: IgnoreMatcher | None = None,
    skipped: list[ScanSkip] | None = None,
) -> list[ScannedFile]:
    root = Path(root)
    matcher = matcher or IgnoreMatcher.default()
    results: list[ScannedFile] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        ignore_reason = matcher.reason(rel)
        if ignore_reason:
            if skipped is not None:
                skipped.append(ScanSkip(rel.as_posix(), ignore_reason))
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size > _MAX_FILE_SIZE:
            if skipped is not None:
                skipped.append(ScanSkip(rel.as_posix(), f"max_size:{_MAX_FILE_SIZE}"))
            continue
        language = detect_language(path)
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        digest = hashlib.sha1(raw).hexdigest()
        symbols: list[ScannedSymbol] = []
        if language == "php":
            try:
                text = raw.decode("utf-8", errors="replace")
                symbols = extract_php_symbols(text)
            except Exception:
                symbols = []
        results.append(
            ScannedFile(
                path=rel.as_posix(),
                absolute_path=path,
                language=language,
                size=stat.st_size,
                hash=digest,
                last_modified=str(int(stat.st_mtime)),
                symbols=symbols,
            )
        )
    return results
