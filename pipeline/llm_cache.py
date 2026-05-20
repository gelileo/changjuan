"""LLM response cache — keyed by (model, prompt_template_version, normalized request JSON).

Phase 1 builds the cache primitives without any LLM client. Phase 2 (stage 3
extraction) wires the cache around its calls.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid


def cache_key(*, model: str, prompt_template_version: str, request: dict) -> str:  # type: ignore[type-arg]
    payload = json.dumps(
        {"model": model, "pv": prompt_template_version, "req": request},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def put(
    conn: sqlite3.Connection,
    key: str,
    *,
    model: str,
    prompt_template_version: str,
    request: dict,  # type: ignore[type-arg]
    response: dict,  # type: ignore[type-arg]
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0,
) -> None:
    conn.execute(
        """
        INSERT INTO llm_cache
            (id, key_hash, model, prompt_template_version,
             request_json, response_json, tokens_in, tokens_out, cost_usd)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (key_hash) DO NOTHING;
        """,
        (
            f"lc:{uuid.uuid4().hex[:12]}",
            key,
            model,
            prompt_template_version,
            json.dumps(request, ensure_ascii=False, sort_keys=True),
            json.dumps(response, ensure_ascii=False, sort_keys=True),
            tokens_in,
            tokens_out,
            cost_usd,
        ),
    )


def get(conn: sqlite3.Connection, key: str) -> dict | None:  # type: ignore[type-arg]
    row = conn.execute("SELECT response_json FROM llm_cache WHERE key_hash = ?;", (key,)).fetchone()
    if row is None:
        return None
    return json.loads(row["response_json"])  # type: ignore[no-any-return]
