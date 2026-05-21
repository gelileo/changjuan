"""extract pre-flight: validates env, prints copy-paste skill invocation."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from pipeline.cli import app


def test_preflight_fails_when_no_corpus(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    runner = CliRunner()
    result = runner.invoke(app, ["extract", "--chapter", "1", "--repo-root", str(tmp_path)])
    assert result.exit_code != 0
    assert "✗" in result.stdout


def test_preflight_fails_when_chapter_has_no_chunks(tmp_path: Path) -> None:
    from pipeline.db import open_corpus_db

    (tmp_path / "data").mkdir()
    open_corpus_db(tmp_path / "data" / "corpus.sqlite")  # empty corpus
    runner = CliRunner()
    result = runner.invoke(app, ["extract", "--chapter", "1", "--repo-root", str(tmp_path)])
    assert result.exit_code != 0
    assert "✗" in result.stdout


def test_preflight_passes_when_chunks_and_skill_present(tmp_path: Path) -> None:
    """All preconditions met → exit 0 + skill invocation in output."""
    import yaml

    from pipeline.db import open_corpus_db
    from pipeline.schemas.extract_output import EXTRACT_OUTPUT_SCHEMA

    (tmp_path / "data").mkdir()
    corpus = open_corpus_db(tmp_path / "data" / "corpus.sqlite")
    corpus.execute(
        "INSERT INTO documents"
        " (id, corpus, title, chapter_num, chapter_title, raw_text, source_edition, ingested_at)"
        " VALUES (1, 'dongzhoulieguozhi', 't', 1, 'ch1', '...', 'test', datetime('now'))"
    )
    # Need >1 chunk to pass the regression check (post _PARA_SEP fix).
    corpus.execute(
        "INSERT INTO chunks (id, document_id, paragraph_start, paragraph_end, text, hash) "
        "VALUES ('chk:dzl:1:0', 1, 0, 5, 't1', 'h1')"
    )
    corpus.execute(
        "INSERT INTO chunks (id, document_id, paragraph_start, paragraph_end, text, hash) "
        "VALUES ('chk:dzl:1:5', 1, 5, 10, 't2', 'h2')"
    )
    corpus.commit()

    # Skill skeleton
    skill_dir = tmp_path / ".claude" / "skills" / "changjuan-extract"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# stub", encoding="utf-8")
    (skill_dir / "system-prompt.md").write_text("# stub", encoding="utf-8")
    (skill_dir / "extraction-schema.yaml").write_text(
        yaml.safe_dump(EXTRACT_OUTPUT_SCHEMA, allow_unicode=True, sort_keys=True),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["extract", "--chapter", "1", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    assert "✓" in result.stdout
    assert "/changjuan-extract" in result.stdout
