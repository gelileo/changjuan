from pipeline.schemas.extract_output import EXTRACT_OUTPUT_SCHEMA as SCHEMA


def test_top_level_has_groups_not_states() -> None:
    props = SCHEMA["properties"]
    assert isinstance(props, dict)
    assert "groups" in props and "states" not in props
    required = SCHEMA["required"]
    assert isinstance(required, list)
    assert "groups" in required and "states" not in required


def test_group_schema_has_type_not_group_type() -> None:
    """Extraction provides the corpus-derived sub-classification as 'type'.
    The collective kind (group_type) is set by the loader from the active profile,
    not extracted — so it must NOT appear in the extraction schema.
    """
    # EXTRACT_OUTPUT_SCHEMA is typed as dict[str, object]; drill in via cast.
    from typing import Any, cast

    schema_props = cast(dict[str, Any], SCHEMA["properties"])
    groups_schema = cast(dict[str, Any], schema_props["groups"])
    group_item_schema = cast(dict[str, Any], groups_schema["items"])
    group_props = cast(dict[str, Any], group_item_schema["properties"])
    assert "type" in group_props, "'type' must be an extraction field on groups"
    assert "group_type" not in group_props, "'group_type' must NOT be in the extraction schema"
