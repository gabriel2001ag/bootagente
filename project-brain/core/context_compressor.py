from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass

from core.context_builder import TaskContext


@dataclass
class ContextMetrics:
    knowledge_hits: int
    rules_reused: int
    patterns_reused: int
    lessons_reused: int
    similar_tasks: int
    files_scanned: int
    files_selected: int
    symbols_selected: int
    context_before_filter: int
    context_after_filter: int
    estimated_context_reduction_percent: float


@dataclass
class CompressedContext:
    payload: dict
    metrics: ContextMetrics


class ContextCompressor:
    """Creates a bounded handoff payload and character-based reduction metrics."""

    def __init__(
        self, max_rules: int = 5, max_patterns: int = 3,
        max_lessons: int = 5, max_similar_tasks: int = 3, max_files: int = 12,
    ):
        self.max_rules = max_rules
        self.max_patterns = max_patterns
        self.max_lessons = max_lessons
        self.max_similar_tasks = max_similar_tasks
        self.max_files = max_files

    def compress(self, context: TaskContext) -> CompressedContext:
        full = dataclasses.asdict(context)
        selected = {
            "task": dataclasses.asdict(context.task),
            "rules": [dataclasses.asdict(x) for x in context.rules[: self.max_rules]],
            "patterns": [dataclasses.asdict(x) for x in context.patterns[: self.max_patterns]],
            "lessons": [dataclasses.asdict(x) for x in context.lessons[: self.max_lessons]],
            "similar_tasks": [
                {"task_id": x.task.id, "title": x.task.title, "score": x.score}
                for x in context.similar_tasks[: self.max_similar_tasks]
            ],
            "candidate_files": context.candidate_files[: self.max_files],
            "keywords": context.keywords,
            "known_risks": list(dict.fromkeys(context.known_risks)),
        }
        before = len(json.dumps(full, ensure_ascii=False, default=str))
        after = len(json.dumps(selected, ensure_ascii=False, default=str))
        reduction = round(100 * max(0, before - after) / before, 2) if before else 0.0
        metrics = ContextMetrics(
            knowledge_hits=len(context.rules) + len(context.patterns) + len(context.lessons),
            rules_reused=len(selected["rules"]),
            patterns_reused=len(selected["patterns"]),
            lessons_reused=len(selected["lessons"]),
            similar_tasks=len(selected["similar_tasks"]),
            files_scanned=len(context.candidate_files),
            files_selected=len(selected["candidate_files"]),
            symbols_selected=0,
            context_before_filter=before,
            context_after_filter=after,
            estimated_context_reduction_percent=reduction,
        )
        return CompressedContext(selected, metrics)

