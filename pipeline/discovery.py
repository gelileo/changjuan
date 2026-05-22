"""Scan corpus.sqlite for Eastern-Zhou state-name occurrences in given chapters.

Used by Phase 4b to build the reign-table worklist. CLI wrapper at
`scripts/discover-states`.
"""

from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

STATE_NAMES: dict[str, str] = {
    "周": "sta:zhou",
    "鲁": "sta:lu",
    "晋": "sta:jin",
    "齐": "sta:qi",
    "楚": "sta:chu",
    "秦": "sta:qin",
    "宋": "sta:song",
    "郑": "sta:zheng",
    "卫": "sta:wei",
    "陈": "sta:chen",
    "蔡": "sta:cai",
    "曹": "sta:cao",
    "燕": "sta:yan",
    "吴": "sta:wu",
    "越": "sta:yue",
    "申": "sta:shen",
}


def discover_states_for_chapters(
    corpus_path: Path,
    chapters: list[int],
) -> list[dict[str, Any]]:
    """Return [{state_id, count, chapters}] for state names appearing in given chapters.

    `count` is the total substring occurrences across all chunks of all given chapters.
    `chapters` is the sorted list of chapter_nums in which the state appears at least once.
    """
    conn = sqlite3.connect(corpus_path)
    placeholders = ",".join("?" * len(chapters))
    rows = conn.execute(
        f"SELECT d.chapter_num, c.text FROM chunks c "
        f"JOIN documents d ON c.document_id = d.id "
        f"WHERE d.chapter_num IN ({placeholders})",
        chapters,
    ).fetchall()
    conn.close()

    per_state_count: dict[str, int] = defaultdict(int)
    per_state_chapters: dict[str, set[int]] = defaultdict(set)
    for chapter_num, text in rows:
        for char, state_id in STATE_NAMES.items():
            n = text.count(char)
            if n > 0:
                per_state_count[state_id] += n
                per_state_chapters[state_id].add(chapter_num)

    out: list[dict[str, Any]] = []
    for state_id, count in per_state_count.items():
        out.append(
            {
                "state_id": state_id,
                "count": count,
                "chapters": sorted(per_state_chapters[state_id]),
            }
        )
    out.sort(key=lambda r: (-r["count"], r["state_id"]))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--chapters",
        required=True,
        help="Comma-separated chapter numbers, e.g. '2,3,4,5'",
    )
    parser.add_argument(
        "--corpus",
        default="data/corpus.sqlite",
        type=Path,
        help="Path to corpus.sqlite",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=0,
        help="Only emit states with count >= this threshold",
    )
    args = parser.parse_args()
    chapters = [int(c) for c in args.chapters.split(",")]
    rows = discover_states_for_chapters(args.corpus, chapters)
    print("state_id\tcount\tchapters")
    for r in rows:
        if r["count"] >= args.min_count:
            chs = ",".join(str(c) for c in r["chapters"])
            print(f"{r['state_id']}\t{r['count']}\t{chs}")


if __name__ == "__main__":
    main()
