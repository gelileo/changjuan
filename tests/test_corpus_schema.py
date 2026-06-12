import sqlite3
from pathlib import Path

SCHEMA = Path("pipeline/schemas/corpus_schema.sql").read_text(encoding="utf-8")


def test_corpus_label_is_free_no_enum_check():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    c.execute(
        "INSERT INTO documents "
        "(id, corpus, title, chapter_num, chapter_title, raw_text, source_edition) "
        "VALUES ('hlm:1','honglou','红楼梦',1,'第一回','...','hlm/json')"
    )
    assert c.execute("SELECT corpus FROM documents WHERE id='hlm:1'").fetchone()[0] == "honglou"
