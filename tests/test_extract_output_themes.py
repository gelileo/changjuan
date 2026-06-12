from typing import Any, cast

from pipeline.schemas.extract_output import EXTRACT_OUTPUT_SCHEMA as SCHEMA


def test_themes_is_an_optional_top_level_array() -> None:
    props = cast(dict[str, Any], SCHEMA["properties"])
    assert "themes" in props
    assert props["themes"]["type"] == "array"
    required = cast(list[str], SCHEMA["required"])
    assert "themes" not in required


def test_theme_item_shape() -> None:
    props = cast(dict[str, Any], SCHEMA["properties"])
    item = cast(dict[str, Any], props["themes"]["items"])
    item_props = cast(dict[str, Any], item["properties"])
    assert "name" in item_props
    assert "occurrences" in item_props
