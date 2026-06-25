import pytest
from validation_replay import _normalize_label


@pytest.mark.parametrize("input,expected", [
    ("通过", "approve"),
    ("approve", "approve"),
    ("条件通过", "conditional"),
    ("conditional", "conditional"),
    ("拒绝", "reject"),
    ("reject", "reject"),
    ("有条件", "conditional"),
    ("", ""),
    ("unknown", "unknown"),
])
def test_normalize_label(input, expected):
    assert _normalize_label(input) == expected
