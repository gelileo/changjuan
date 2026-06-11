from pipeline.schemas.extract_output import EXTRACT_OUTPUT_SCHEMA as SCHEMA


def test_top_level_has_groups_not_states() -> None:
    props = SCHEMA["properties"]
    assert isinstance(props, dict)
    assert "groups" in props and "states" not in props
    required = SCHEMA["required"]
    assert isinstance(required, list)
    assert "groups" in required and "states" not in required
