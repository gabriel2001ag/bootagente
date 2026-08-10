from brain.similarity import KeywordSimilarityEngine, tokenize
from core.task import Task


def _task(id_, title, description="", category="unknown", source="cli"):
    return Task(id=id_, project_id=1, title=title, description=description, category=category, source=source)


def test_tokenize_strips_stopwords_and_short_tokens():
    tokens = tokenize("Limitar a impressão de pedidos para no máximo 50")
    assert "a" not in tokens
    assert "de" not in tokens
    assert "limitar" in tokens
    assert "impressão" in tokens or "impressao" in tokens


def test_similar_tasks_score_higher_than_unrelated():
    engine = KeywordSimilarityEngine()
    new_task = _task(1, "limitar intervalo das notas para 100", category="validation")
    similar = _task(2, "limitar intervalo dos pedidos para 50", category="validation")
    unrelated = _task(3, "corrigir layout do menu lateral", category="ui")

    score_similar = engine.compare(new_task, similar)
    score_unrelated = engine.compare(new_task, unrelated)

    assert score_similar > score_unrelated
    assert 0.0 <= score_similar <= 1.0
    assert 0.0 <= score_unrelated <= 1.0


def test_identical_task_text_scores_high():
    engine = KeywordSimilarityEngine()
    t1 = _task(1, "limitar intervalo de pedidos", category="validation")
    t2 = _task(2, "limitar intervalo de pedidos", category="validation")
    assert engine.compare(t1, t2) >= 0.9


def test_completely_disjoint_tasks_score_zero_or_near_zero():
    engine = KeywordSimilarityEngine()
    t1 = _task(1, "abc def ghi", category="unknown", source="cli")
    t2 = _task(2, "xyz uvw rst", category="database", source="senior")
    # No shared tokens, no shared category, no shared source -> only the
    # floor contributed by nothing matching at all: exactly 0.0.
    assert engine.compare(t1, t2) == 0.0


def test_same_source_alone_does_not_create_similarity():
    engine = KeywordSimilarityEngine()
    first = _task(1, "ola", source="chat")
    second = _task(2, "protocolo lunar inedito", source="chat")
    assert engine.compare(first, second) == 0.0
