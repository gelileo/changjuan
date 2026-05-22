"""Date parser: explicit_reign_other resolution against per-state YAML reign tables."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
import structlog

from pipeline.dates import (
    load_reign_yaml,
    resolve_explicit_reign_other,
)

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "reigns" / "sta_test.yaml"


@pytest.fixture(autouse=True)
def _structlog_to_stdlib() -> None:
    """Route structlog through stdlib logging so pytest's caplog can capture it."""
    structlog.configure(
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )


@pytest.fixture(autouse=True)
def _force_reign_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect the reign loader to look in a tmp directory."""
    reigns_dir = tmp_path / "data" / "reigns"
    reigns_dir.mkdir(parents=True)
    (reigns_dir / "sta_test.yaml").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("CHANGJUAN_REIGN_DIR", str(reigns_dir))
    from pipeline import dates

    dates._REIGN_YAML_CACHE.clear()
    return reigns_dir


def test_resolves_by_id() -> None:
    year = resolve_explicit_reign_other(
        state_id="sta:test",
        ruler_ref="测试武公",
        reign_year=1,
    )
    assert year == 715


def test_resolves_by_posthumous_name() -> None:
    year = resolve_explicit_reign_other(
        state_id="sta:test",
        ruler_ref="武公",
        reign_year=1,
    )
    assert year == 715


def test_resolves_by_given_name() -> None:
    year = resolve_explicit_reign_other(
        state_id="sta:test",
        ruler_ref="一郎",
        reign_year=1,
    )
    assert year == 715


def test_resolves_year_n_offsets_correctly() -> None:
    year = resolve_explicit_reign_other(
        state_id="sta:test",
        ruler_ref="测试武公",
        reign_year=5,
    )
    assert year == 711


def test_returns_none_when_state_yaml_missing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        year = resolve_explicit_reign_other(
            state_id="sta:nonexistent",
            ruler_ref="某公",
            reign_year=1,
        )
    assert year is None
    assert any(
        "reign_table_missing" in r.message or "nonexistent" in r.message for r in caplog.records
    )


def test_returns_none_when_ruler_ref_not_found(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        year = resolve_explicit_reign_other(
            state_id="sta:test",
            ruler_ref="不存在的公",
            reign_year=1,
        )
    assert year is None
    assert any(
        "ruler_ref_not_found" in r.message or "不存在的公" in r.message for r in caplog.records
    )


def test_returns_year_but_warns_when_reign_year_out_of_range(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        year = resolve_explicit_reign_other(
            state_id="sta:test",
            ruler_ref="测试武公",
            reign_year=50,
        )
    assert year == 666
    assert any("reign_year_out_of_range" in r.message for r in caplog.records)


def test_load_reign_yaml_parses_fixture() -> None:
    data = load_reign_yaml("sta:test")
    assert data is not None
    assert data["state_id"] == "sta:test"
    rulers = data["rulers"]
    assert isinstance(rulers, list)
    assert len(rulers) == 3
    first = rulers[0]
    assert isinstance(first, dict)
    assert first["reign_start_bce"] == 715
