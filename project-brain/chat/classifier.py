"""Small deterministic classifier that runs before the technical router."""
from __future__ import annotations

from enum import Enum

from core.concepts import ConceptExpander
from core.config import ConceptsConfig, LanguageConfig
from core.nlp import ACTION_FIX, ACTION_IMPLEMENT, PortugueseNLP
from core.text_normalizer import PortugueseTextNormalizer


class ChatMessageCategory(str, Enum):
    GREETING = "GREETING"
    CASUAL_CHAT = "CASUAL_CHAT"
    COMMAND = "COMMAND"
    STATUS_QUERY = "STATUS_QUERY"
    MEMORY_QUERY = "MEMORY_QUERY"
    CODE_QUESTION = "CODE_QUESTION"
    ANALYSIS_TASK = "ANALYSIS_TASK"
    IMPLEMENTATION_TASK = "IMPLEMENTATION_TASK"
    SELF_QUERY = "SELF_QUERY"
    UNKNOWN = "UNKNOWN"


def _default_nlp() -> PortugueseNLP:
    concepts = ConceptsConfig()
    language = LanguageConfig()
    expander = ConceptExpander(concepts.groups, concepts.aliases, concepts.relationships)
    return PortugueseNLP(expander, PortugueseTextNormalizer(language.replacements), language.actions)


class ChatMessageClassifier:
    greetings = {"ola", "oi", "bom dia", "boa tarde", "boa noite"}
    casual = {"tudo bem", "obrigado", "obrigada", "valeu", "como vai"}
    analysis_terms = {
        "analise", "analisa", "analisar", "investigue", "investigar", "mapeie", "mapear",
    }
    implementation_terms = {
        "implemente", "implementar", "altere", "alterar", "corrija", "corrigir",
        "adicione", "adicionar", "remova", "remover",
    }
    code_terms = {"codigo", "arquivo", "classe", "funcao", "controller", "model", "service"}
    domain_terms = {
        "pedido", "pedidos", "nfe", "nf", "fiscal", "financeiro", "estoque", "produto",
        "cte", "nfce",
    }
    self_anchors = {
        "voce", "vc", "seu", "sua", "brain", "senior", "sessao",
    }
    self_predicates = {
        "quem", "qual", "que", "online", "offline", "modo", "capaz", "pode", "memoria",
        "status", "funciona", "sabe", "aprende", "fale", "conte",
    }
    status_queries = {
        "status", "status do projeto", "status do brain", "status do project brain",
        "status da sessao", "qual o status do projeto", "qual o status do brain",
        "qual o status da sessao",
    }

    def __init__(self, nlp: PortugueseNLP | None = None):
        self.nlp = nlp or _default_nlp()

    def classify(self, message: str) -> ChatMessageCategory:
        normalized = self.nlp.normalizer.normalize(message)
        if message.lstrip().startswith("/"):
            return ChatMessageCategory.COMMAND
        tokens = set(normalized.split())
        # Technical intent wins over a greeting in mixed phrases.
        if tokens & self.implementation_terms:
            return ChatMessageCategory.IMPLEMENTATION_TASK
        if tokens & self.analysis_terms:
            return ChatMessageCategory.ANALYSIS_TASK
        if tokens & self.code_terms:
            return ChatMessageCategory.CODE_QUESTION
        # A domain entity makes an otherwise generic "qual/status" question technical.
        if tokens & self.domain_terms and tokens & {"qual", "status", "como", "porque"}:
            return ChatMessageCategory.CODE_QUESTION
        if (
            tokens & self.self_anchors
            and tokens & self.self_predicates
            and not (tokens & self.domain_terms)
        ):
            return ChatMessageCategory.SELF_QUERY
        if normalized in self.status_queries:
            return ChatMessageCategory.STATUS_QUERY
        if "memoria" in tokens or "memory" in tokens:
            return ChatMessageCategory.MEMORY_QUERY
        if normalized in self.greetings:
            return ChatMessageCategory.GREETING
        if normalized.rstrip("?").strip() in self.casual:
            return ChatMessageCategory.CASUAL_CHAT
        return self._interpret_unknown(message)

    def _interpret_unknown(self, message: str) -> ChatMessageCategory:
        """PLN fallback (seção 10): only overrides UNKNOWN, and only when a
        known domain concept was actually recognized — never turns a truly
        generic phrase into a technical task just because a verb matched."""
        understanding = self.nlp.interpret(message)
        if not understanding.concepts:
            return ChatMessageCategory.UNKNOWN
        if understanding.action in {ACTION_FIX, ACTION_IMPLEMENT}:
            return ChatMessageCategory.IMPLEMENTATION_TASK
        if understanding.action:
            return ChatMessageCategory.ANALYSIS_TASK
        return ChatMessageCategory.CODE_QUESTION
