from brain.lessons import Lesson
from brain.memory import SimilarTask
from brain.patterns import Pattern
from brain.rules import Rule
from core.context_builder import TaskContext
from core.context_compressor import ContextCompressor
from core.task import Task


def test_context_compressor_bounds_knowledge_and_reports_character_metrics():
    task = Task(id=2, project_id=1, title="Alterar itens de pedido", description="")
    previous = Task(id=1, project_id=1, title="Analisar fluxo de pedidos", description="")
    context = TaskContext(
        task=task,
        rules=[
            Rule(id=i, rule_code=f"R{i}", category="orders", rule_text="x" * 100)
            for i in range(8)
        ],
        patterns=[
            Pattern(id=i, pattern_code=f"P{i}", category="orders", framework=None, trigger="pedido")
            for i in range(5)
        ],
        lessons=[
            Lesson(id=i, lesson_code=f"L{i}", problem="p" * 100, solution="s" * 100)
            for i in range(7)
        ],
        similar_tasks=[SimilarTask(previous, 0.8)],
        candidate_files=[f"app/File{i}.php" for i in range(20)],
    )

    result = ContextCompressor(max_rules=3, max_patterns=2, max_lessons=3, max_files=4).compress(context)

    assert len(result.payload["rules"]) == 3
    assert len(result.payload["patterns"]) == 2
    assert len(result.payload["lessons"]) == 3
    assert len(result.payload["candidate_files"]) == 4
    assert result.metrics.context_after_filter < result.metrics.context_before_filter
    assert result.metrics.estimated_context_reduction_percent > 0

