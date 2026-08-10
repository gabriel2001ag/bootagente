"""SearchAgent: text/file/symbol search, preferring ripgrep with a pure
Python fallback (seção 17).

Never raises because `rg` is missing — degrades gracefully, so callers
never need to special-case tool availability.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agents.base_agent import Agent, AgentResult
from analysis.code_scanner import IgnoreMatcher, should_ignore
from brain.similarity import tokenize
from core.enums import AgentResultStatus
from core.task import Task

_MAX_MATCHES = 200
_TEXT_EXTENSIONS = {
    ".php", ".js", ".ts", ".sql", ".py", ".json", ".yaml", ".yml", ".html",
    ".twig", ".md", ".txt", ".env",
}


@dataclass
class TextMatch:
    file: str
    line: int
    text: str


class SearchAgent(Agent):
    name = "search_agent"

    def __init__(self, project_root: Path, matcher: IgnoreMatcher | None = None):
        self.project_root = Path(project_root)
        self.matcher = matcher or IgnoreMatcher.default()

    @staticmethod
    def rg_available() -> bool:
        return shutil.which("rg") is not None

    # -- public search API ------------------------------------------------
    def search_text(self, query: str, max_results: int = _MAX_MATCHES) -> list[TextMatch]:
        if self.rg_available():
            return self._search_text_rg(query, max_results)
        return self._search_text_python(query, max_results)

    def search_files_by_name(self, fragment: str, max_results: int = 50) -> list[str]:
        fragment_lower = fragment.lower()
        matches = []
        for path in self.project_root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(self.project_root)
            if should_ignore(rel, self.matcher):
                continue
            if fragment_lower in path.name.lower():
                matches.append(rel.as_posix())
                if len(matches) >= max_results:
                    break
        return matches

    # -- Agent interface ----------------------------------------------------
    def run(self, task: Task, context) -> AgentResult:
        keywords = sorted(tokenize(f"{task.title} {task.description}"))
        if not keywords:
            return AgentResult(AgentResultStatus.NO_MATCH, 0.0, "no keywords extracted from task")

        candidate_files: dict[str, int] = {}
        matches_sample: list[TextMatch] = []
        for keyword in keywords[:8]:  # cap to keep it fast/deterministic
            for match in self.search_text(keyword, max_results=30):
                candidate_files[match.file] = candidate_files.get(match.file, 0) + 1
                if len(matches_sample) < 20:
                    matches_sample.append(match)
            for file_path in self.search_files_by_name(keyword, max_results=10):
                candidate_files[file_path] = candidate_files.get(file_path, 0) + 2

        ranked = sorted(candidate_files.items(), key=lambda kv: kv[1], reverse=True)
        top_files = [f for f, _ in ranked[:15]]
        # Keep relevance absolute: a lone text hit scores 1/7 for one
        # keyword and remains below the default 0.20 code threshold.
        maximum_possible = max(1, len(keywords[:8]) * 7)
        ranked_files = [
            {"file": file_path, "score": round(min(1.0, score / maximum_possible), 4)}
            for file_path, score in ranked[:15]
        ]

        if not top_files:
            return AgentResult(
                AgentResultStatus.NO_MATCH, 0.0, "no candidate files found for task keywords",
                data={"keywords": keywords},
            )

        return AgentResult(
            AgentResultStatus.OK,
            confidence=min(1.0, 0.3 + 0.1 * len(top_files)),
            message=f"found {len(top_files)} candidate file(s)",
            data={
                "keywords": keywords,
                "candidate_files": top_files,
                "ranked_files": ranked_files,
                "sample_matches": [m.__dict__ for m in matches_sample],
            },
        )

    # -- implementations ----------------------------------------------------
    def _search_text_rg(self, query: str, max_results: int) -> list[TextMatch]:
        args = [
            "rg", "--line-number", "--no-heading", "--max-count", "5",
            "-g", "!vendor", "-g", "!node_modules", "-g", "!.git",
            "-F", "-i", "--", query, str(self.project_root),
        ]
        try:
            result = subprocess.run(
                args, capture_output=True, encoding="utf-8", errors="replace", timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired):
            return self._search_text_python(query, max_results)
        if result.returncode not in (0, 1):
            return self._search_text_python(query, max_results)
        matches: list[TextMatch] = []
        for line in result.stdout.splitlines():
            # A non-greedy path group skips the drive-letter colon on Windows
            # and stops at the first ``:<digits>:`` line-number delimiter.
            parsed = re.match(r"^(.+?):(\d+):(.*)$", line)
            if parsed is None:
                continue
            file_abs, line_no, text = parsed.groups()
            try:
                rel = Path(file_abs).resolve().relative_to(self.project_root.resolve()).as_posix()
            except ValueError:
                rel = file_abs
            if should_ignore(rel, self.matcher):
                continue
            matches.append(TextMatch(file=rel, line=int(line_no), text=text.strip()))
            if len(matches) >= max_results:
                break
        return matches

    def _search_text_python(self, query: str, max_results: int) -> list[TextMatch]:
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        matches: list[TextMatch] = []
        for path in self.project_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _TEXT_EXTENSIONS:
                continue
            rel = path.relative_to(self.project_root)
            if should_ignore(rel, self.matcher):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    matches.append(TextMatch(file=rel.as_posix(), line=i, text=line.strip()))
                    if len(matches) >= max_results:
                        return matches
        return matches
