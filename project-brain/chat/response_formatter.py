"""Natural pt-BR response formatting (seção 13-18).

Turns a `TaskRunSummary` + `Understanding` into a friendly explanation of
what the Brain understood and why it chose a given route, instead of raw
`Route: SENIOR` / `Decision: REQUIRES_SENIOR` labels. Internal implementation
details (provider name, session id, handoff mechanics, raw route/decision
labels) never appear in the default reply — only in the `/verbose on`
technical block appended at the end.
"""
from __future__ import annotations

from core.nlp import ACTION_ANALYZE, ACTION_FIX, ACTION_IMPLEMENT, ACTION_SHOW_STATUS, Understanding
from core.orchestrator import TaskRunSummary

_ACTION_PHRASES = {
    ACTION_ANALYZE: "analisar",
    ACTION_SHOW_STATUS: "saber em que ponto está",
    ACTION_FIX: "corrigir um problema em",
    ACTION_IMPLEMENT: "implementar algo em",
}


def _intro(understanding: Understanding) -> str:
    action_phrase = _ACTION_PHRASES.get(understanding.action, "ajudar com sua pergunta sobre")
    domain_phrase = f" a implementação de {understanding.domain.upper()}" if understanding.domain else ""
    if understanding.action == ACTION_SHOW_STATUS and understanding.domain:
        subject = f"{action_phrase} {understanding.domain}"
    elif understanding.domain:
        subject = f"{action_phrase}{domain_phrase or (' ' + understanding.domain)}"
    else:
        subject = "sua mensagem"
    scope_phrase = " na branch atual" if "CURRENT_BRANCH" in understanding.scope else ""
    return f"Entendi que você quer {subject}{scope_phrase}."


def _evidence_summary(summary: TaskRunSummary) -> str | None:
    context = summary.context
    parts = []
    if context.rules:
        parts.append(f"{len(context.rules)} regra(s)")
    if context.patterns:
        parts.append(f"{len(context.patterns)} padrão(ões)")
    if context.lessons:
        parts.append(f"{len(context.lessons)} lição(ões)")
    if context.similar_tasks:
        parts.append(f"{len(context.similar_tasks)} task(s) anterior(es)")
    if context.candidate_files:
        parts.append(f"{len(context.candidate_files)} arquivo(s) do projeto")
    return ", ".join(parts) if parts else None


def _body_paragraph(summary: TaskRunSummary, route: str) -> str:
    """One clean paragraph per route — no repetition between an "evidence"
    sentence and a "route" sentence, they used to say the same thing twice."""
    evidence = _evidence_summary(summary)
    if route == "LOCAL":
        base = "Já tenho conhecimento suficiente para responder sozinho, sem precisar do Codex."
        return f"{base} Baseei essa resposta em: {evidence}." if evidence else base
    if route == "ANALYSIS_ONLY":
        base = (
            "Já tenho conhecimento suficiente para uma análise, mas não vou alterar "
            "nada — apenas relatar o que sei."
        )
        return f"{base} Baseei essa análise em: {evidence}." if evidence else base
    if route == "HYBRID":
        base = (
            "Já conheço boa parte do problema, mas preciso do Codex somente para a "
            "parte que ainda não está registrada no Brain."
        )
        return f"{base} Já tenho: {evidence}." if evidence else base
    if route == "SENIOR":
        base = (
            "Entendi sua solicitação, mas ainda não tenho conhecimento suficiente para "
            "concluir isso sozinho. Vou precisar do Codex Senior para analisar a parte "
            "que ainda não conheço."
        )
        files = len(summary.context.candidate_files)
        if files:
            base += (
                f" Encontrei {files} arquivo(s) relacionados no ERP, mas isso ainda não "
                "é evidência suficiente para responder com segurança sozinho."
            )
        return base
    if route == "WAITING_FOR_SENIOR":
        return (
            "Entendi o que você precisa, mas não tenho conhecimento suficiente para "
            "continuar sozinho e o Codex está indisponível no momento. Vou manter esta "
            "tarefa pendente até o Senior estar disponível."
        )
    return f"Rota: {route}"


def _learning_note(route: str) -> str:
    if route in {"SENIOR", "HYBRID"}:
        return (
            "Depois que a análise for aprovada, esse conhecimento poderá ser "
            "armazenado no Brain para que perguntas parecidas exijam menos investigação."
        )
    return ""


class NaturalResponseFormatter:
    @staticmethod
    def format(
        summary: TaskRunSummary,
        understanding: Understanding,
        route: str,
        technical_block: str,
        verbose: bool,
    ) -> str:
        paragraphs = [_intro(understanding), "", _body_paragraph(summary, route)]
        note = _learning_note(route)
        if note:
            paragraphs += ["", note]
        paragraphs += [
            "",
            "Estado atual:",
            f"- Área: {understanding.domain or '(não identificada)'}",
            f"- Confiança de entendimento: {understanding.intent_confidence * 100:.0f}%",
            f"- Confiança de conhecimento: {summary.confidence * 100:.0f}%",
            f"- Task: #{summary.task.id}",
        ]
        if verbose:
            paragraphs += ["", "--- detalhes técnicos (/verbose off para ocultar) ---", technical_block]
        return "\n".join(paragraphs)
