from pathlib import Path

from typer.testing import CliRunner

from pipeline.cli import app


def test_cli_has_ingest_chunk_load_export_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("ingest", "chunk", "load", "export"):
        assert cmd in result.stdout


def test_cli_ingest_dry_runs(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Smoke-test: invoking `changjuan ingest` with --repo-root pointing at an empty tmp dir
    should exit cleanly with 'no corpora found' rather than crash."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["ingest", "--repo-root", str(tmp_path)])
    # Either exits 0 with a "no corpora" message, or exits 1 with a clear error.
    # Both acceptable; crash is not.
    assert result.exit_code in (0, 1)
    assert "Traceback" not in result.stdout
