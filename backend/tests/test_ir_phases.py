from skill_ir import normalize_step_phase, VALID_STEP_PHASES


def test_normalize_step_phase_english():
    assert normalize_step_phase("Customer Filter") == "customer_filter"


def test_normalize_step_phase_chinese():
    assert normalize_step_phase("客户筛选") == "customer_filter"


def test_normalize_step_phase_case_insensitive():
    assert normalize_step_phase("DATA_MATCH") == "data_match"


def test_normalize_step_phase_all_canonicals_are_english():
    for phase in VALID_STEP_PHASES:
        assert phase == phase.lower()
        assert phase in ("customer_filter", "data_match", "attribution", "decision")
