from pathlib import Path

_HERE = Path(__file__).parent

CORPUS_SCHEMA: str = (_HERE / "corpus_schema.sql").read_text(encoding="utf-8")
CANONICAL_SCHEMA: str = (_HERE / "canonical_schema.sql").read_text(encoding="utf-8")
