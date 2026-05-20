from pathlib import Path

from pipeline.db import apply_schema, connect
from pipeline.llm_cache import cache_key, get, put
from pipeline.schemas import CANONICAL_SCHEMA


def test_cache_key_is_stable() -> None:
    k1 = cache_key(model="claude-sonnet", prompt_template_version="v1", request={"prompt": "hi"})
    k2 = cache_key(model="claude-sonnet", prompt_template_version="v1", request={"prompt": "hi"})
    k3 = cache_key(model="claude-sonnet", prompt_template_version="v2", request={"prompt": "hi"})
    assert k1 == k2
    assert k1 != k3


def test_put_then_get_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "changjuan.sqlite"
    with connect(db) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        key = cache_key(model="m", prompt_template_version="v", request={"x": 1})
        put(
            conn,
            key,
            model="m",
            prompt_template_version="v",
            request={"x": 1},
            response={"ok": True},
        )
        got = get(conn, key)
    assert got == {"ok": True}


def test_get_miss_returns_none(tmp_path: Path) -> None:
    db = tmp_path / "changjuan.sqlite"
    with connect(db) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        assert get(conn, "nope") is None
