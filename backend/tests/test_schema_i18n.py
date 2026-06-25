from shared import get_schema_path
import yaml


def test_english_schema_exists():
    path = get_schema_path("en")
    assert path.exists()
    assert path.name == "scenario-schema.en.yaml"


def test_english_schema_loads():
    path = get_schema_path("en")
    with open(path, "r", encoding="utf-8") as f:
        schema = yaml.safe_load(f)
    assert schema["display_name"] == "Generic Knowledge Extraction Structure"
    assert "Decision Rule" in schema["categories"]
    field_names = {f["name"] for f in schema["fields"]}
    assert "method" in field_names
    assert "confidence" in field_names
    confidence_field = next(f for f in schema["fields"] if f["name"] == "confidence")
    assert confidence_field["enum_values"] == ["high", "medium", "low"]
