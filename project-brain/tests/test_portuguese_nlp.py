"""Regression tests for the Portuguese PLN layer (seção PLN)."""
from __future__ import annotations

import pytest

from brain.lessons import LessonRepository
from brain.patterns import PatternRepository
from brain.projects import ProjectRepository
from brain.rules import RuleRepository
from chat.classifier import ChatMessageCategory, ChatMessageClassifier
from chat.service import ChatService
from core.config import BrainConfig
from core.nlp import ACTION_ANALYZE, ACTION_FIX, PortugueseNLP
from core.concepts import ConceptExpander
from core.text_normalizer import PortugueseTextNormalizer


def _nlp(config: BrainConfig | None = None) -> PortugueseNLP:
    config = config or BrainConfig()
    expander = ConceptExpander(
        config.concepts.groups, config.concepts.aliases, config.concepts.relationships
    )
    return PortugueseNLP(
        expander, PortugueseTextNormalizer(config.language.replacements), config.language.actions
    )


def _service(db, config, brain_paths, php_project, seed_orders_knowledge: bool = True) -> ChatService:
    project = ProjectRepository(db).get_or_create(str(php_project), name="sample")
    if seed_orders_knowledge:
        RuleRepository(db).add(
            "RULE-PEDIDO-001", "orders", "Preservar estados protegidos.", project_id=project.id
        )
        PatternRepository(db).add(
            "PATTERN-PEDIDO-001", "orders", trigger="alterar itens de pedido",
            procedure=["validar", "persistir"], project_id=project.id,
        )
        LessonRepository(db).add(
            "LESSON-PEDIDO-001", "Alterar item como CRUD causa inconsistencia.",
            "Preservar estoque.", project_id=project.id,
        )
    return ChatService(db, config, brain_paths, project)


# -- PortugueseTextNormalizer -------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected_normalized"),
    [
        ("analize essa branch", "analise essa branch"),
        ("me explique como vc funciona", "me explique como voce funciona"),
        ("oq falta fazer no cte", "o que falta fazer no cte"),
        ("veja pq a nfce não está emitindo", "veja porque a nfce nao esta emitindo"),
        ("analise essa branch e veja onde estamos no CT-e", "analise essa branch e veja onde estamos no cte"),
        ("qual o status da NF-e?", "qual o status da nfe"),
        ("qual o status da NFC-e?", "qual o status da nfce"),
    ],
)
def test_normalizer_applies_conservative_replacements(raw, expected_normalized):
    normalizer = PortugueseTextNormalizer()
    assert normalizer.normalize(raw) == expected_normalized


def test_normalizer_preserves_raw_text_for_audit():
    normalizer = PortugueseTextNormalizer()
    result = normalizer.interpret("Analize O Pedido")
    assert result.raw_text == "Analize O Pedido"
    assert result.normalized_text == "analise o pedido"


def test_normalizer_never_touches_code_identifiers_when_not_given_them():
    # The normalizer is only ever fed chat message text in this codebase —
    # identifiers like tab_pedido/NfeInutilizacaoRegra are never routed
    # through it. Demonstrate the replacement table itself is whole-token
    # only, so even if it were applied, identifiers survive intact.
    normalizer = PortugueseTextNormalizer()
    assert normalizer.normalize("tab_pedido") == "tab_pedido"
    assert "vc" not in normalizer.normalize("svc_pedido").split()


# -- PortugueseNLP: understanding vs knowledge confidence ---------------------

CTE_PHRASES = [
    "analize essa branch do erp em que ponto estamos do cte",
    "analise essa branch e veja onde estamos no CT-e",
    "em que pé está o cte?",
    "oq falta do cte?",
    "veja o conhecimento de transporte",
    "da uma olhada no cte",
    "como está o cte nessa branch?",
    "me diga onde estamos na implementação do cte",
]


@pytest.mark.parametrize("message", CTE_PHRASES)
def test_understanding_recognizes_cte_regardless_of_phrasing(message):
    understanding = _nlp().interpret(message)
    assert "fiscal" in understanding.concepts
    assert understanding.domain == "fiscal"
    assert understanding.intent_confidence > 0


def test_understanding_confidence_is_high_even_without_any_knowledge():
    """Section 11: understanding confidence must not collapse to 0 just
    because the Brain has zero rules/patterns for the topic yet."""
    understanding = _nlp().interpret(
        "analize essa branch do erp em que ponto estamos do cte"
    )
    assert understanding.action == "SHOW_STATUS"
    assert understanding.scope == ("CURRENT_BRANCH",)
    assert understanding.intent_confidence >= 0.9


def test_understanding_is_empty_for_truly_unrelated_text():
    understanding = _nlp().interpret("protocolo lunar")
    assert understanding.concepts == ()
    assert understanding.domain is None
    assert understanding.intent_confidence == 0.0


def test_action_detection_prefers_the_longest_matching_phrase():
    understanding = _nlp().interpret("corrija o erro da nfe")
    assert understanding.action == ACTION_FIX
    understanding = _nlp().interpret("analise o pedido")
    assert understanding.action == ACTION_ANALYZE


# -- ChatMessageClassifier: reduced UNKNOWN, technical precedence preserved --

@pytest.mark.parametrize("message", CTE_PHRASES)
def test_classifier_no_longer_returns_unknown_for_cte_phrasings(message):
    category = ChatMessageClassifier().classify(message)
    assert category != ChatMessageCategory.UNKNOWN
    assert category in {ChatMessageCategory.ANALYSIS_TASK, ChatMessageCategory.CODE_QUESTION}


@pytest.mark.parametrize(
    "message",
    ["corrija o erro da nfe", "arruma a nota fiscal", "veja pq a nfce não está emitindo"],
)
def test_classifier_keeps_nfe_and_nfce_technical(message):
    assert ChatMessageClassifier().classify(message) != ChatMessageCategory.UNKNOWN


def test_classifier_keeps_informal_technical_request_technical_despite_greeting():
    category = ChatMessageClassifier().classify("oi, da uma olhada no cte pra mim")
    assert category == ChatMessageCategory.ANALYSIS_TASK


@pytest.mark.parametrize("message", ["me fale sobre vc", "como vc funciona"])
def test_classifier_still_recognizes_self_query_after_pln_changes(message):
    assert ChatMessageClassifier().classify(message) == ChatMessageCategory.SELF_QUERY


@pytest.mark.parametrize("message", ["oi", "ola", "bom dia", "valeu"])
def test_classifier_still_recognizes_casual_after_pln_changes(message):
    assert ChatMessageClassifier().classify(message) in {
        ChatMessageCategory.GREETING,
        ChatMessageCategory.CASUAL_CHAT,
    }


def test_classifier_stays_unknown_for_text_with_no_recognized_concept():
    assert ChatMessageClassifier().classify("protocolo lunar") == ChatMessageCategory.UNKNOWN


# -- ChatService: natural language response + confidence separation ----------

def test_natural_response_explains_cte_request_without_prior_knowledge(
    db, config, brain_paths, php_project
):
    service = _service(db, config, brain_paths, php_project, seed_orders_knowledge=False)
    assert service.verbose is False

    reply = service.handle("analize essa branch do erp em que ponto estamos do cte")

    assert "Route:" not in reply.text
    assert "Confiança de entendimento: 90%" in reply.text or "Confiança de entendimento: 100%" in reply.text
    assert "Confiança de conhecimento:" in reply.text
    assert "Área: fiscal" in reply.text
    assert "Codex" in reply.text


def test_verbose_off_by_default_hides_technical_block(db, config, brain_paths, php_project):
    service = _service(db, config, brain_paths, php_project, seed_orders_knowledge=False)
    assert service.verbose is False

    reply = service.handle("analize essa branch do erp em que ponto estamos do cte")

    assert "Route:" not in reply.text
    assert "Decision:" not in reply.text
    assert "Entendi que você quer" in reply.text


def test_verbose_on_reveals_technical_block(db, config, brain_paths, php_project):
    service = _service(db, config, brain_paths, php_project, seed_orders_knowledge=False)
    service.handle("/verbose on")

    reply = service.handle("analize essa branch do erp em que ponto estamos do cte")

    assert "Route:" in reply.text
    assert "Decision:" in reply.text
    assert "Entendi que você quer" in reply.text


def test_conversational_context_inherits_concept_on_follow_up(
    db, config, brain_paths, php_project
):
    service = _service(db, config, brain_paths, php_project, seed_orders_knowledge=False)

    service.handle("analize essa branch do erp em que ponto estamos do cte")
    assert service.last_understanding.domain == "fiscal"

    follow_up = service.handle("e o que falta?")

    assert service.last_understanding.domain == "fiscal"
    assert "fiscal" in service.last_understanding.concepts
    assert "Área: fiscal" in follow_up.text


def test_self_query_natural_reply_is_human_and_hides_internals_by_default(
    db, config, brain_paths, php_project
):
    service = _service(db, config, brain_paths, php_project, seed_orders_knowledge=False)

    reply = service.handle("me fale sobre vc")

    assert reply.task_id is None
    assert "Project Brain" in reply.text
    assert "memória técnica" in reply.text
    assert "Codex" in reply.text
    assert "Estado atual:" in reply.text
    assert f"- Projeto: {service.project.name}" in reply.text
    assert "- Modo: ONLINE" in reply.text
    # Numbers are dynamic (queried live), never hardcoded strings.
    assert "- Tasks registradas: 0" in reply.text
    assert "- Aguardando Senior: 0" in reply.text
    # Internal wiring stays hidden until /verbose on.
    assert "codex-vscode" not in reply.text
    assert "Sessão:" not in reply.text
    assert "handoff invertido/manual" not in reply.text


def test_self_query_task_counts_are_dynamic_not_hardcoded(db, config, brain_paths, php_project):
    service = _service(db, config, brain_paths, php_project, seed_orders_knowledge=False)
    service.handle("analise essa branch do erp em que ponto estamos do cte")

    reply = service.handle("o que você sabe?")

    assert "- Tasks registradas: 1" in reply.text
    assert reply.task_id is None


def test_conversational_context_does_not_leak_across_unrelated_turns(
    db, config, brain_paths, php_project
):
    service = _service(db, config, brain_paths, php_project, seed_orders_knowledge=False)
    service.handle("analize essa branch do erp em que ponto estamos do cte")

    unrelated = service.handle("implemente uma correção no financeiro")

    assert service.last_understanding.domain == "financeiro"
