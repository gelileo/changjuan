from pathlib import Path

from pipeline import config
from pipeline.config import Config


def test_config_default_paths(tmp_path: Path) -> None:
    cfg = Config(repo_root=tmp_path)
    assert cfg.corpus_db == tmp_path / "data" / "corpus.sqlite"
    assert cfg.canonical_db == tmp_path / "data" / "changjuan.sqlite"
    assert cfg.exports_dir == tmp_path / "data" / "exports"
    assert cfg.corpora_dir == tmp_path / "corpora"


def test_config_chunk_overlap_defaults() -> None:
    cfg = Config()
    assert cfg.chunk_target_chars == 1800
    assert cfg.chunk_overlap_chars == 200


def test_phase2_constants_exist() -> None:
    assert isinstance(config.EXTRACTION_DIR, str)
    assert 0 < config.QA_SAMPLE_FRACTION < 1
    assert config.QA_SAMPLE_FLOOR < config.QA_SAMPLE_CEILING
    assert 0 < config.QA_MISMATCH_THRESHOLD < 1
    for kind in ("person", "event", "place", "state", "relation"):
        assert kind in config.GOLDEN_PR_THRESHOLDS
        for metric in ("precision", "recall"):
            v = config.GOLDEN_PR_THRESHOLDS[kind][metric]
            assert 0 < v <= 1
