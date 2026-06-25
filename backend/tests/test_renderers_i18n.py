from i18n_render import report_label


def test_report_label_english():
    assert report_label("report_quality_title", "en").startswith("# Knowledge Extraction Quality Report")


def test_report_label_chinese():
    assert report_label("report_quality_title", "zh-CN").startswith("# 知识萃取质量报告")


def test_report_label_confidence():
    assert report_label("report_confidence_high", "en") == "High"
    assert report_label("report_confidence_high", "zh-CN") == "高"
