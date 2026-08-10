from brain.memory import MemoryStore
from brain.patterns import PatternRepository
from brain.projects import ProjectRepository
from brain.similarity import KeywordSimilarityEngine
from core.concepts import ConceptExpander
from core.config import BrainConfig
from core.enums import RoutingMode, SeniorStatus
from core.routing import ConfidenceEngine, SmartRouter, TaskClassifier
from core.task import Task


def _task(task_id: int, title: str) -> Task:
    return Task(id=task_id, project_id=1, title=title, description="")


def test_concept_expansion_connects_task_1_to_task_2():
    cfg = BrainConfig()
    expander = ConceptExpander(cfg.concepts.groups, cfg.concepts.aliases)
    engine = KeywordSimilarityEngine(concept_expander=expander)
    task_1 = _task(1, "Analisar o fluxo de pedidos do ERP sem implementar alteracoes")
    task_2 = _task(2, "Analisar o que considerar antes de alterar itens de um pedido existente")

    assert "orders" in expander.expand(task_2.title).concepts
    assert engine.compare(task_2, task_1) >= cfg.retrieval.similar_tasks_min_score


def test_pattern_retrieval_tokenizes_trigger_and_procedure(db):
    project_id = ProjectRepository(db).get_or_create("/tmp/v3", name="v3").id
    PatternRepository(db).add(
        "P-ORDER", "draft-to-aggregate",
        trigger="Criação ou edição de pedido com itens",
        procedure=["Persistir pedido e movimentar estoque"],
        project_id=project_id,
    )
    memory = MemoryStore(db, KeywordSimilarityEngine())

    matches = memory.search_patterns(
        _task(1, "alterar itens de pedido e estoque"), project_id, limit=3
    )

    assert [item.pattern_code for item in matches] == ["P-ORDER"]


def test_smart_router_exposes_all_primary_routes():
    cfg = BrainConfig()
    classifier = TaskClassifier(ConceptExpander(cfg.concepts.groups, cfg.concepts.aliases))
    analysis = classifier.classify(_task(1, "Analisar pedidos e estoque"))
    change = classifier.classify(_task(2, "Alterar pedido"))
    router = SmartRouter()

    assert router.route(analysis, 0.5, SeniorStatus.UNAVAILABLE).mode == RoutingMode.ANALYSIS_ONLY
    assert router.route(change, 0.9, SeniorStatus.UNAVAILABLE).mode == RoutingMode.LOCAL
    assert router.route(change, 0.9, SeniorStatus.AVAILABLE).mode == RoutingMode.HYBRID
    assert router.route(change, 0.3, SeniorStatus.AVAILABLE).mode == RoutingMode.SENIOR
    assert router.route(change, 0.3, SeniorStatus.UNAVAILABLE).mode == RoutingMode.WAITING_FOR_SENIOR


def test_confidence_engine_reports_explainable_signals():
    context = type("Context", (), {
        "similar_tasks": [], "rules": [], "patterns": [], "lessons": [],
    })()
    result = ConfidenceEngine().calculate(context, validation_confidence=0.0, concept_count=2)

    assert result.signals["concepts"] == 1.0
    assert result.confidence == 0.1
    assert any(reason.startswith("concepts=") for reason in result.reasons)


def test_weak_memory_overlap_is_filtered_by_configured_threshold(db):
    project_id = ProjectRepository(db).get_or_create("/tmp/weak", name="weak").id
    from brain.rules import RuleRepository
    RuleRepository(db).add(
        "WEAK", "general",
        "pedido completamente alheio sobre exportação histórica",
        project_id=project_id,
    )
    memory = MemoryStore(db, KeywordSimilarityEngine())
    task = _task(1, "analisar pedido estoque financeiro fiscal itens")

    assert memory.search_rules(task, project_id, min_score=0.5) == []


def test_weak_single_code_hit_is_filtered_by_configured_threshold(
    db, config, brain_paths, php_project
):
    project = ProjectRepository(db).get_or_create(str(php_project), name="sample")
    from core.orchestrator import Orchestrator

    task = Task(
        id=-1, project_id=project.id, title="buscarPorId", description="", source="chat"
    )
    context = Orchestrator(db, config, brain_paths, project).context_builder.build(
        task, project.id
    )

    assert context.candidate_files == []


def test_weak_pattern_lesson_and_similar_task_are_filtered_by_threshold(db):
    from brain.lessons import LessonRepository

    project_id = ProjectRepository(db).get_or_create("/tmp/weak-all", name="weak-all").id
    PatternRepository(db).add(
        "P-WEAK", "general", trigger="pedido histórico sem relação",
        project_id=project_id,
    )
    LessonRepository(db).add(
        "L-WEAK", "pedido histórico sem relação", "consultar arquivo legado",
        project_id=project_id,
    )
    tasks = MemoryStore(db, KeywordSimilarityEngine()).tasks
    previous = tasks.create(project_id, "pedido histórico sem relação")
    task = Task(
        id=-1, project_id=project_id,
        title="analisar pedido estoque financeiro fiscal itens", description="",
    )
    memory = MemoryStore(db, KeywordSimilarityEngine())

    assert memory.search_patterns(task, project_id, min_score=0.8) == []
    assert memory.search_lessons(task, project_id, min_score=0.8) == []
    assert memory.search_similar_tasks(task, project_id, min_score=0.8) == []
