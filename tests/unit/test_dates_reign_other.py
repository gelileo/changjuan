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


def test_parse_date_dispatches_to_explicit_reign_other(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """parse_date should route '<state><ruler>X年' patterns through resolve_explicit_reign_other."""
    # Set up a synthetic jin reign YAML in the redirected dir.
    reigns_dir = tmp_path / "data" / "reigns"
    if not reigns_dir.exists():
        reigns_dir.mkdir(parents=True)
    (reigns_dir / "sta_jin.yaml").write_text(
        """state_id: sta:jin
state_name: 晋
sources: [synthetic]
rulers:
  - id: 晋文公
    posthumous_name: 文公
    given_name: 重耳
    reign_start_bce: 636
    reign_end_bce: 628
    sources: [synthetic]
    confidence: high
    notes: ""
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("CHANGJUAN_REIGN_DIR", str(reigns_dir))
    from pipeline import dates

    dates._REIGN_YAML_CACHE.clear()

    d = dates.parse_date("晋文公七年")
    assert d["inference_kind"] == "explicit_reign_other"
    assert d["year_bce"] == 630  # 636 - (7 - 1)
    assert d["original"] == "晋文公七年"


def test_parse_date_explicit_reign_other_falls_through_when_state_yaml_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If the state has no YAML, parse_date falls through (returns unknown) — doesn't crash."""
    reigns_dir = tmp_path / "data" / "reigns"
    if not reigns_dir.exists():
        reigns_dir.mkdir(parents=True)
    # No sta_chu.yaml written.
    monkeypatch.setenv("CHANGJUAN_REIGN_DIR", str(reigns_dir))
    from pipeline import dates

    dates._REIGN_YAML_CACHE.clear()

    d = dates.parse_date("楚庄王三年")
    # Without a reign table, falls through. May land in unknown or remain
    # explicit_reign_other-but-year_bce-None depending on resolver behavior;
    # the contract is "doesn't crash, returns a valid DateDict".
    assert "inference_kind" in d
    assert d.get("year_bce") is None
