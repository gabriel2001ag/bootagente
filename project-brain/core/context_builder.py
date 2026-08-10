"""ContextBuilder: assembles the minimal working memory for a task
(seções 20 e 21 — "redução de tokens").

This is what would be sent to a real Senior in V2: never the whole
project, only what local search/memory already narrowed down. The same
object is reused by the local fallback pipeline, so both paths share one
source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agents.search_agent import SearchAgent
from brain.lessons import Lesson
from brain.memory import MemoryStore, SimilarTask
from brain.patterns import Pattern
from brain.projects import ProjectRepository
from brain.rules import Rule
from core.task import Task
from core.config import IndexingConfig
from analysis.code_scanner import IgnoreMatcher
from git.git_service import GitService, GitStatus


@dataclass
class TaskContext:
    task: Task
    rules: list[Rule] = field(default_factory=list)
    patterns: list[Pattern] = field(default_factory=list)
    lessons: list[Lesson] = field(default_factory=list)
    similar_tasks: list[SimilarTask] = field(default_factory=list)
    candidate_files: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    git_status: GitStatus | None = None
    known_risks: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"TASK: {self.task.title}",
            f"RULES: {len(self.rules)} item(s)",
            f"PATTERNS: {len(self.patterns)} item(s)",
            f"LESSONS: {len(self.lessons)} item(s)",
            f"SIMILAR TASKS: {len(self.similar_tasks)} item(s)",
            f"FILES: {', '.join(self.candidate_files) or '(none found)'}",
        ]
        if self.git_status:
            lines.append(
                f"GIT STATUS: branch={self.git_status.branch} dirty={self.git_status.dirty}"
            )
        if self.known_risks:
            lines.append(f"KNOWN RISKS: {'; '.join(self.known_risks)}")
        return "\n".join(lines)


class ContextBuilder:
    def __init__(
        self,
        memory: MemoryStore,
        project_root: Path,
        indexing: IndexingConfig | None = None,
        project_id: int | None = None,
        retrieval=None,
    ):
        self.memory = memory
        self.retrieval = retrieval
        self.project_root = Path(project_root)
        indexing = indexing or IndexingConfig()
        ignored_dirs, ignored_globs, sensitive_globs = (
            indexing.for_project(project_id) if project_id else (
                indexing.ignored_dirs, indexing.ignored_globs, indexing.sensitive_globs
            )
        )
        self.search_agent = SearchAgent(
            project_root,
            IgnoreMatcher.from_config(ignored_dirs, ignored_globs, sensitive_globs),
        )

    def build(self, task: Task, project_id: int) -> TaskContext:
        rules = self.memory.search_rules(
            task, project_id, getattr(self.retrieval, "rules_limit", None),
            getattr(self.retrieval, "rules_min_score", 0.0),
        )
        patterns = self.memory.search_patterns(
            task, project_id, getattr(self.retrieval, "patterns_limit", None),
            getattr(self.retrieval, "patterns_min_score", 0.0),
        )
        lessons = self.memory.search_lessons(
            task, project_id, getattr(self.retrieval, "lessons_limit", None),
            getattr(self.retrieval, "lessons_min_score", 0.0),
        )
        similar_tasks = self.memory.search_similar_tasks(
            task, project_id,
            limit=getattr(self.retrieval, "similar_tasks_limit", 5),
            min_score=getattr(self.retrieval, "similar_tasks_min_score", 0.15),
        )
        keywords = self.memory.keywords_for(task)

        search_result = self.search_agent.run(task, context=None)
        ranked_files = search_result.data.get("ranked_files", [])
        if ranked_files:
            code_min_score = getattr(self.retrieval, "code_min_score", 0.0)
            candidate_files = [
                item["file"] for item in ranked_files if item["score"] >= code_min_score
            ]
        else:
            candidate_files = list(search_result.data.get("candidate_files", []))

        git_status = None
        if GitService.is_git_available():
            git_status = GitService(self.project_root).status()

        known_risks: list[str] = []
        if git_status and git_status.has_pre_existing_changes:
            known_risks.append(
                "PRE_EXISTING_CHANGE: project has uncommitted changes before this task started"
            )
        for lesson in lessons:
            if lesson.category == "risk" or "risco" in (lesson.problem or "").lower():
                known_risks.append(f"lesson {lesson.lesson_code}: {lesson.problem}")

        return TaskContext(
            task=task,
            rules=rules,
            patterns=patterns,
            lessons=lessons,
            similar_tasks=similar_tasks,
            candidate_files=candidate_files,
            keywords=keywords,
            git_status=git_status,
            known_risks=known_risks,
        )
