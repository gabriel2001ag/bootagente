"""MemoryStore: facade over rules/patterns/lessons/tasks search (seção 15).

This is what the local fallback pipeline (and ContextBuilder) query instead
of ever sending the whole project to a Senior. Everything here is plain
SQL + deterministic scoring — no ML.
"""
from __future__ import annotations

from dataclasses import dataclass

from brain.database import Database
from brain.lessons import Lesson, LessonRepository
from brain.patterns import Pattern, PatternRepository
from brain.rules import Rule, RuleRepository
from brain.similarity import SimilarityEngine, tokenize
from core.task import Task, TaskRepository


@dataclass
class SimilarTask:
    task: Task
    score: float


class MemoryStore:
    def __init__(self, db: Database, similarity_engine: SimilarityEngine, concept_expander=None):
        self.db = db
        self.similarity_engine = similarity_engine
        self.concept_expander = concept_expander
        self.rules = RuleRepository(db)
        self.patterns = PatternRepository(db)
        self.lessons = LessonRepository(db)
        self.tasks = TaskRepository(db)

    def keywords_for(self, task: Task) -> list[str]:
        text = f"{task.title} {task.description}"
        if self.concept_expander is not None:
            return sorted(self.concept_expander.expand(text).expanded_tokens)
        return sorted(tokenize(text))

    @staticmethod
    def _overlap_score(query: set[str], text: str, confidence: float = 1.0) -> float:
        haystack = set(tokenize(text))
        if not query or not haystack:
            return 0.0
        overlap = len(query & haystack)
        return round((overlap / max(1, min(len(query), len(haystack)))) * confidence, 4)

    def search_rules(
        self, task: Task, project_id: int, limit: int | None = None,
        min_score: float = 0.0,
    ) -> list[Rule]:
        query = set(self.keywords_for(task))
        ranked = [
            (self._overlap_score(
                query, f"{item.category} {item.condition or ''} {item.rule_text}",
                item.confidence,
            ), item)
            for item in self.rules.list_approved(project_id)
        ]
        ranked = [item for item in ranked if item[0] >= min_score and item[0] > 0]
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [item for _, item in ranked[:limit]]

    def search_lessons(
        self, task: Task, project_id: int, limit: int | None = None,
        min_score: float = 0.0,
    ) -> list[Lesson]:
        query = set(self.keywords_for(task))
        ranked = [
            (self._overlap_score(
                query, f"{item.category} {item.problem} {item.solution}", item.confidence
            ), item)
            for item in self.lessons.list_approved(project_id)
        ]
        ranked = [item for item in ranked if item[0] >= min_score and item[0] > 0]
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [item for _, item in ranked[:limit]]

    def search_patterns(
        self, task: Task, project_id: int, limit: int | None = None,
        min_score: float = 0.0,
    ) -> list[Pattern]:
        # Patterns match by category/trigger rather than free text, since
        # they represent reusable procedures, not free-form notes.
        candidates = self.patterns.list_approved(project_id=project_id)
        keywords = set(self.keywords_for(task))
        matched: list[tuple[int, Pattern]] = []
        for pattern in candidates:
            haystack = set(tokenize(
                " ".join([pattern.category, pattern.trigger or "", *pattern.procedure])
            ))
            score = self._overlap_score(
                keywords, " ".join([pattern.category, pattern.trigger or "", *pattern.procedure]),
                pattern.confidence,
            )
            if score >= min_score and score > 0:
                matched.append((score, pattern))
        matched.sort(key=lambda item: (item[0], item[1].confidence), reverse=True)
        return [pattern for _, pattern in matched[:limit]]

    def search_similar_tasks(
        self, task: Task, project_id: int, limit: int = 5, min_score: float = 0.15
    ) -> list[SimilarTask]:
        history = [
            t for t in self.tasks.list_for_project(project_id, limit=200) if t.id != task.id
        ]
        scored = [
            SimilarTask(task=prev, score=self.similarity_engine.compare(task, prev))
            for prev in history
        ]
        scored = [s for s in scored if s.score >= min_score]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:limit]
