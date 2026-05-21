"""changjuan re-extract — reload-only mode + missing-file user-instruction path."""

from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from pipeline.cli import app


def _seed_corpus_with_one_chunk(tmp_path: Path) -> None:
    from pipeline.db import open_canonical_db, open_corpus_db

    (tmp_path / "data").mkdir()
    corpus = open_corpus_db(tmp_path / "data" / "corpus.sqlite")
    open_canonical_db(tmp_path / "data" / "changjuan.sqlite")
    corpus.execute(
        "INSERT INTO documents "
        "(id, corpus, title, chapter_num, chapter_title, raw_text, source_edition, ingested_at) "
        "VALUES (1, 'dongzhoulieguozhi', 't', 1, 'ch1', '...', 'test', datetime('now'))"
    )
    corpus.execute(
        "INSERT INTO chunks (id, document_id, paragraph_start, paragraph_end, text, hash) "
        "VALUES ('chk:ch01-001', 1, 1, 1, 't', 'h')"
    )
    corpus.commit()


def test_missing_extraction_file_instructs_user(tmp_path: Path) -> None:
    _seed_corpus_with_one_chunk(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "re-extract",
            "--chapter",
            "1",
            "--prompt-version",
            "v2",
            "--repo-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code != 0
    combined = result.stdout + (result.stderr or "")
    assert "Invoke" in combined or "Claude Code" in combined
    assert "changjuan-extract" in combined  # the skill name


def test_reload_when_file_exists(tmp_path: Path) -> None:
    _seed_corpus_with_one_chunk(tmp_path)
    extract_dir = tmp_path / "data" / "extractions" / "ch01"
    extract_dir.mkdir(parents=True)
    (extract_dir / "extract-v1.yaml").write_text(
        yaml.safe_dump({"persons": [], "events": [], "places": [], "states": [], "relations": []}),
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "re-extract",
            "--chapter",
            "1",
            "--prompt-version",
            "v1",
            "--repo-root",
            str(tmp_path),
        ],
    )
    # Empty payload: should exit 0 (validator passes, zero records written)
    assert result.exit_code == 0, result.stdout
