from pathlib import Path

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
