"""Global Project Brain configuration (seção 28).

`config.yaml` holds *global* defaults (confidence thresholds, safety,
senior provider selection, learning flags). It intentionally does not
pin a single project path — see ARCHITECTURE.md section 2 for why: the
`projects` table + `state.json` handle the "active project" concept so a
single Brain installation can track multiple target projects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ConfidenceThresholds:
    auto_execute: float = 0.95
    requires_review: float = 0.80
    analysis_only: float = 0.60


@dataclass
class SafetyConfig:
    allow_destructive_commands: bool = False


@dataclass
class SeniorConfig:
    provider: str = "codex-vscode"
    enabled: bool = True
    # Only used by MockSeniorProvider to make offline/online demos possible
    # without touching real credentials.
    mock_availability: str = "AVAILABLE"


@dataclass
class FallbackConfig:
    enabled: bool = True


@dataclass
class ConceptsConfig:
    groups: dict[str, list[str]] = field(default_factory=lambda: {
        "orders": ["pedido", "pedidos", "orcamento", "orçamento", "item", "itens"],
        "inventory": ["estoque", "lote", "saldo", "movimentacao", "movimentação"],
        "finance": ["financeiro", "parcela", "parcelas", "boleto", "baixa"],
        "fiscal": [
            "fiscal", "tributo", "tributos", "cfop", "nfe", "nf-e", "nota",
            "cte", "ct-e", "nfce", "nfc-e", "conhecimento", "transporte",
        ],
        "analysis": ["analisar", "analise", "análise", "mapear", "investigar"],
        "change": ["alterar", "editar", "incluir", "remover", "corrigir"],
    })
    aliases: dict[str, str] = field(default_factory=lambda: {
        "orcamentos": "orders",
        "orçamentos": "orders",
        "venda": "orders",
        "vendas": "orders",
        "produto": "inventory",
        "produtos": "inventory",
        "financeira": "finance",
        "financeiras": "finance",
        "nota_fiscal": "fiscal",
    })
    relationships: dict[str, dict[str, float]] = field(default_factory=lambda: {
        "orders": {"inventory": 0.8, "finance": 0.7, "fiscal": 0.7},
    })


@dataclass
class LanguageConfig:
    """PLN layer vocabulary (seção PLN) — kept out of Python so it can grow
    without code changes. `replacements` are conservative whole-token
    rewrites (abbreviation/typo -> canonical form); `actions` map a
    canonical action name to the pt-BR phrases that trigger it."""

    replacements: dict[str, str] = field(default_factory=lambda: {
        "vc": "voce",
        "vcs": "voces",
        "oq": "o que",
        "pq": "porque",
        "analize": "analise",
        "analizar": "analisar",
        "concerte": "conserte",
        "ero": "erro",
        "brench": "branch",
    })
    actions: dict[str, list[str]] = field(default_factory=lambda: {
        "ANALYZE": [
            "analisar", "analise", "verificar", "veja", "olhar", "dar uma olhada",
            "da uma olhada", "conferir", "avaliar", "investigar", "investigue", "mapear",
        ],
        "SHOW_STATUS": [
            "como esta", "em que ponto", "em que pe", "onde estamos",
            "o que falta", "ate onde foi", "status",
        ],
        "FIX": ["corrigir", "corrija", "arrumar", "resolver", "consertar", "conserte"],
        "IMPLEMENT": ["implementar", "implemente", "criar", "adicionar", "incluir"],
    })


@dataclass
class RetrievalConfig:
    rules_limit: int = 10
    patterns_limit: int = 10
    lessons_limit: int = 10
    similar_tasks_limit: int = 5
    similar_tasks_min_score: float = 0.10
    rules_min_score: float = 0.20
    patterns_min_score: float = 0.20
    lessons_min_score: float = 0.10
    code_min_score: float = 0.20


@dataclass
class LearningConfig:
    automatic_after_approval: bool = True


@dataclass
class GitConfig:
    required: bool = True


@dataclass
class QAConfig:
    run_php_lint: bool = True
    run_composer_test: bool = False
    run_phpunit: bool = False


@dataclass
class IndexingProjectOverride:
    mode: str = "add"
    ignored_dirs: list[str] = field(default_factory=list)
    ignored_globs: list[str] = field(default_factory=list)
    sensitive_globs: list[str] = field(default_factory=list)


@dataclass
class IndexingConfig:
    ignored_dirs: list[str] = field(default_factory=lambda: [
        ".git", "vendor", "node_modules", "storage", "writable", "writable_*",
        "logs", "log", "cache", "sessions", "session", "tmp", "temp",
        "coverage", "dist", "build", ".vscode", ".idea", "__pycache__",
        ".venv", "venv", ".agents", ".codex",
    ])
    ignored_globs: list[str] = field(default_factory=lambda: [
        "AGENTS*.md", "agedev.md", "reviewer.md", "docs/agentes/**",
        "public/uploads/**", "public/cache/**", "public/tmp/**",
    ])
    sensitive_globs: list[str] = field(default_factory=lambda: [
        ".env", ".env.*", "*.log", "*.sqlite", "*.sqlite3", "*.db",
        "*.session", "*.cache",
    ])
    project_overrides: dict[str, IndexingProjectOverride] = field(default_factory=dict)

    def for_project(self, project_id: int) -> tuple[list[str], list[str], list[str]]:
        override = self.project_overrides.get(str(project_id))
        if override is None:
            return (
                list(self.ignored_dirs),
                list(self.ignored_globs),
                list(self.sensitive_globs),
            )
        if override.mode not in {"add", "replace"}:
            raise ValueError(f"Invalid indexing override mode for project {project_id}: {override.mode}")
        if override.mode == "replace":
            return (
                list(override.ignored_dirs),
                list(override.ignored_globs),
                list(override.sensitive_globs),
            )
        return (
            list(dict.fromkeys([*self.ignored_dirs, *override.ignored_dirs])),
            list(dict.fromkeys([*self.ignored_globs, *override.ignored_globs])),
            list(dict.fromkeys([*self.sensitive_globs, *override.sensitive_globs])),
        )


@dataclass
class BrainConfig:
    confidence: ConfidenceThresholds = field(default_factory=ConfidenceThresholds)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    senior: SeniorConfig = field(default_factory=SeniorConfig)
    fallback: FallbackConfig = field(default_factory=FallbackConfig)
    concepts: ConceptsConfig = field(default_factory=ConceptsConfig)
    language: LanguageConfig = field(default_factory=LanguageConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    learning: LearningConfig = field(default_factory=LearningConfig)
    git: GitConfig = field(default_factory=GitConfig)
    qa: QAConfig = field(default_factory=QAConfig)
    indexing: IndexingConfig = field(default_factory=IndexingConfig)

    @classmethod
    def load(cls, path: Path) -> "BrainConfig":
        if not path.exists():
            cfg = cls()
            cfg.save(path)
            return cfg
        raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        indexing_raw = raw.get("indexing", {})
        overrides = {
            str(project_id): IndexingProjectOverride(**value)
            for project_id, value in indexing_raw.get("project_overrides", {}).items()
        }
        return cls(
            confidence=ConfidenceThresholds(**raw.get("confidence", {})),
            safety=SafetyConfig(**raw.get("safety", {})),
            senior=SeniorConfig(**raw.get("senior", {})),
            fallback=FallbackConfig(**raw.get("fallback", {})),
            concepts=ConceptsConfig(**raw.get("concepts", {})),
            language=LanguageConfig(**raw.get("language", {}).get("pt_br", {})),
            retrieval=RetrievalConfig(**raw.get("retrieval", {})),
            learning=LearningConfig(**raw.get("learning", {})),
            git=GitConfig(**raw.get("git", {})),
            qa=QAConfig(**raw.get("qa", {})),
            indexing=IndexingConfig(
                ignored_dirs=indexing_raw.get("ignored_dirs", IndexingConfig().ignored_dirs),
                ignored_globs=indexing_raw.get("ignored_globs", IndexingConfig().ignored_globs),
                sensitive_globs=indexing_raw.get(
                    "sensitive_globs", IndexingConfig().sensitive_globs
                ),
                project_overrides=overrides,
            ),
        )

    def save(self, path: Path) -> None:
        data = {
            "confidence": self.confidence.__dict__,
            "safety": self.safety.__dict__,
            "senior": self.senior.__dict__,
            "fallback": self.fallback.__dict__,
            "concepts": self.concepts.__dict__,
            "language": {"pt_br": self.language.__dict__},
            "retrieval": self.retrieval.__dict__,
            "learning": self.learning.__dict__,
            "git": self.git.__dict__,
            "qa": self.qa.__dict__,
            "indexing": {
                "ignored_dirs": self.indexing.ignored_dirs,
                "ignored_globs": self.indexing.ignored_globs,
                "sensitive_globs": self.indexing.sensitive_globs,
                "project_overrides": {
                    project_id: override.__dict__
                    for project_id, override in self.indexing.project_overrides.items()
                },
            },
        }
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")

    def decision_for_confidence(self, confidence: float):
        from core.enums import Decision

        if confidence >= self.confidence.auto_execute:
            return Decision.AUTO_EXECUTE_ALLOWED
        if confidence >= self.confidence.requires_review:
            return Decision.PATCH_REQUIRES_REVIEW
        if confidence >= self.confidence.analysis_only:
            return Decision.ANALYSIS_ONLY
        return Decision.REQUIRES_SENIOR
