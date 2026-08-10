from core.config import BrainConfig, IndexingProjectOverride
from core.enums import Decision


def test_default_config_has_expected_thresholds():
    cfg = BrainConfig()
    assert cfg.confidence.auto_execute == 0.95
    assert cfg.confidence.requires_review == 0.80
    assert cfg.confidence.analysis_only == 0.60
    assert cfg.safety.allow_destructive_commands is False


def test_config_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "config.yaml"
    cfg = BrainConfig()
    cfg.confidence.auto_execute = 0.99
    cfg.senior.provider = "codex"
    cfg.indexing.sensitive_globs.append("*.credential")
    cfg.retrieval.rules_min_score = 0.33
    cfg.retrieval.patterns_min_score = 0.34
    cfg.retrieval.lessons_min_score = 0.35
    cfg.retrieval.similar_tasks_min_score = 0.36
    cfg.retrieval.code_min_score = 0.37
    cfg.save(path)

    loaded = BrainConfig.load(path)
    assert loaded.confidence.auto_execute == 0.99
    assert loaded.senior.provider == "codex"
    assert "*.credential" in loaded.indexing.sensitive_globs
    assert loaded.retrieval.rules_min_score == 0.33
    assert loaded.retrieval.patterns_min_score == 0.34
    assert loaded.retrieval.lessons_min_score == 0.35
    assert loaded.retrieval.similar_tasks_min_score == 0.36
    assert loaded.retrieval.code_min_score == 0.37


def test_config_load_creates_file_if_missing(tmp_path):
    path = tmp_path / "config.yaml"
    assert not path.exists()
    BrainConfig.load(path)
    assert path.exists()


def test_decision_thresholds():
    cfg = BrainConfig()
    assert cfg.decision_for_confidence(0.99) == Decision.AUTO_EXECUTE_ALLOWED
    assert cfg.decision_for_confidence(0.95) == Decision.AUTO_EXECUTE_ALLOWED
    assert cfg.decision_for_confidence(0.85) == Decision.PATCH_REQUIRES_REVIEW
    assert cfg.decision_for_confidence(0.65) == Decision.ANALYSIS_ONLY
    assert cfg.decision_for_confidence(0.30) == Decision.REQUIRES_SENIOR


def test_indexing_project_overrides_add_and_replace():
    cfg = BrainConfig()
    cfg.indexing.project_overrides["1"] = IndexingProjectOverride(
        mode="add", ignored_globs=["local/**"], sensitive_globs=["*.secret"]
    )
    _, add_globs, add_sensitive = cfg.indexing.for_project(1)
    assert "AGENTS*.md" in add_globs
    assert "local/**" in add_globs
    assert ".env" in add_sensitive
    assert "*.secret" in add_sensitive

    cfg.indexing.project_overrides["2"] = IndexingProjectOverride(
        mode="replace", ignored_dirs=["cache"], ignored_globs=["*.tmp"],
        sensitive_globs=["credentials.*"],
    )
    dirs, globs, sensitive = cfg.indexing.for_project(2)
    assert dirs == ["cache"]
    assert globs == ["*.tmp"]
    assert sensitive == ["credentials.*"]
