"""ReviewerAgent: rule-based sanity checks over a proposed change (seção 17).

V1 is a first, honest implementation of the rules explicitly listed in the
spec: scope, diff size, sensitive files, syntax errors (via QAAgent
results), test failures, unexpected deletions, destructive migrations.
A richer, learning-informed reviewer is a V2 item.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from agents.base_agent import Agent, AgentResult
from core.enums import AgentResultStatus
from core.task import Task
from git.diff_parser import DiffSummary

SENSITIVE_FILE_PATTERNS = [
    re.compile(r"\.env$"),
    re.compile(r"composer\.lock$"),
    re.compile(r"config[/\\]database\.php$"),
    re.compile(r"[/\\]\.git[/\\]"),
    re.compile(r"[/\\]Migrations[/\\]"),
]

DESTRUCTIVE_MIGRATION_RE = re.compile(
    r"\bdropTable\b|\bDROP\s+TABLE\b|\bDROP\s+DATABASE\b|\bTRUNCATE\b", re.IGNORECASE
)

MAX_FILES_CHANGED = 10
MAX_LINES_CHANGED = 400


@dataclass
class ReviewFinding:
    rule: str
    severity: str  # "warning" | "blocking"
    message: str


@dataclass
class ReviewOutcome:
    findings: list[ReviewFinding] = field(default_factory=list)

    @property
    def has_blocking(self) -> bool:
        return any(f.severity == "blocking" for f in self.findings)


class ReviewerAgent(Agent):
    name = "reviewer_agent"

    def review(
        self,
        expected_files: list[str],
        diff_summary: DiffSummary | None = None,
        qa_ok: bool = True,
        tests_ok: bool = True,
        migration_text: str | None = None,
    ) -> ReviewOutcome:
        outcome = ReviewOutcome()

        if diff_summary is not None:
            changed_paths = [f.path for f in diff_summary.files]

            out_of_scope = [p for p in changed_paths if expected_files and p not in expected_files]
            if out_of_scope:
                outcome.findings.append(
                    ReviewFinding(
                        "scope", "blocking",
                        f"{len(out_of_scope)} file(s) changed outside task scope: {out_of_scope}",
                    )
                )

            if diff_summary.files_changed > MAX_FILES_CHANGED:
                outcome.findings.append(
                    ReviewFinding(
                        "large_diff", "warning",
                        f"{diff_summary.files_changed} files changed (threshold {MAX_FILES_CHANGED})",
                    )
                )
            if diff_summary.total_lines_changed > MAX_LINES_CHANGED:
                outcome.findings.append(
                    ReviewFinding(
                        "large_diff", "warning",
                        f"{diff_summary.total_lines_changed} lines changed (threshold {MAX_LINES_CHANGED})",
                    )
                )

            for path in changed_paths:
                if any(p.search(path) for p in SENSITIVE_FILE_PATTERNS):
                    outcome.findings.append(
                        ReviewFinding("sensitive_file", "blocking", f"sensitive file touched: {path}")
                    )

        if not qa_ok:
            outcome.findings.append(ReviewFinding("syntax_errors", "blocking", "QAAgent reported lint/syntax failures"))
        if not tests_ok:
            outcome.findings.append(ReviewFinding("test_failures", "blocking", "test run reported failures"))

        if migration_text and DESTRUCTIVE_MIGRATION_RE.search(migration_text):
            outcome.findings.append(
                ReviewFinding("destructive_migration", "blocking", "migration contains a destructive statement")
            )

        return outcome

    def run(self, task: Task, context) -> AgentResult:
        outcome = self.review(expected_files=getattr(context, "candidate_files", []) or [])
        if outcome.has_blocking:
            return AgentResult(
                AgentResultStatus.ERROR, 0.0,
                f"{len(outcome.findings)} review finding(s), including blocking issues",
                data={"findings": [f.__dict__ for f in outcome.findings]},
            )
        if outcome.findings:
            return AgentResult(
                AgentResultStatus.OK, 0.7,
                f"{len(outcome.findings)} non-blocking review finding(s)",
                data={"findings": [f.__dict__ for f in outcome.findings]},
            )
        return AgentResult(AgentResultStatus.OK, 1.0, "no review findings")
