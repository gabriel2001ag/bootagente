from brain.lessons import LessonRepository
from brain.patterns import PatternRepository
from brain.rules import RuleRepository


def test_rule_repository_add_and_search(db):
    repo = RuleRepository(db)
    repo.add(
        rule_code="RULE-001",
        category="development",
        rule_text="Never modify functionality outside the task scope.",
        approved=True,
    )
    repo.add(
        rule_code="PARIPASSU-001",
        category="paripassu",
        rule_text="nomeAlternativo is required",
        condition="origem_publica == false",
        dont=["update existing elo unnecessarily"],
        approved=True,
    )

    all_rules = repo.list_approved()
    assert len(all_rules) == 2

    found = repo.search(["paripassu"])
    assert len(found) == 1
    assert found[0].rule_code == "PARIPASSU-001"
    assert found[0].dont == ["update existing elo unnecessarily"]


def test_rule_upsert_by_code(db):
    repo = RuleRepository(db)
    repo.add(rule_code="RULE-002", category="x", rule_text="v1")
    repo.add(rule_code="RULE-002", category="x", rule_text="v2")
    assert repo.get("RULE-002").rule_text == "v2"
    assert len(repo.list_approved()) == 1


def test_pattern_repository_add_and_search_by_trigger(db):
    repo = PatternRepository(db)
    repo.add(
        pattern_code="PATTERN-CI4-VALIDATION-001",
        category="validation",
        framework="CodeIgniter4",
        trigger="numeric_range",
        procedure=["locate controller", "insert backend validation"],
    )
    matches = repo.search_by_trigger("numeric_range")
    assert len(matches) == 1
    assert matches[0].procedure[0] == "locate controller"


def test_lesson_repository_add_and_search(db):
    repo = LessonRepository(db)
    repo.add(
        lesson_code="LESSON-0001",
        problem="intervalo não possuía limite real",
        solution="validar intervalo no backend e frontend",
        files=["app/Controllers/Pedido.php"],
        category="validation",
        validated_by="senior",
    )
    found = repo.search(["intervalo"])
    assert len(found) == 1
    assert found[0].files == ["app/Controllers/Pedido.php"]


def test_project_scoped_vs_global_rules(db):
    from brain.projects import ProjectRepository

    projects = ProjectRepository(db)
    p1 = projects.get_or_create("/tmp/proj1", name="proj1")
    p2 = projects.get_or_create("/tmp/proj2", name="proj2")

    repo = RuleRepository(db)
    repo.add(rule_code="GLOBAL-1", category="general", rule_text="applies everywhere")
    repo.add(rule_code="P1-ONLY", category="general", rule_text="only proj1", project_id=p1.id)

    rules_p1 = repo.list_approved(project_id=p1.id)
    rules_p2 = repo.list_approved(project_id=p2.id)

    assert {r.rule_code for r in rules_p1} == {"GLOBAL-1", "P1-ONLY"}
    assert {r.rule_code for r in rules_p2} == {"GLOBAL-1"}


def test_deprecated_knowledge_is_not_retrieved(db):
    rules = RuleRepository(db)
    patterns = PatternRepository(db)
    lessons = LessonRepository(db)
    rules.add("R-OLD", "orders", "pedido antigo")
    patterns.add("P-OLD", "orders", trigger="pedido antigo")
    lessons.add("L-OLD", "pedido antigo", "não usar")
    db.execute("UPDATE rules SET deprecated=1 WHERE rule_code='R-OLD'")
    db.execute("UPDATE patterns SET deprecated=1 WHERE pattern_code='P-OLD'")
    db.execute("UPDATE lessons SET deprecated=1 WHERE lesson_code='L-OLD'")

    assert rules.search(["pedido"]) == []
    assert patterns.list_approved() == []
    assert lessons.search(["pedido"]) == []
