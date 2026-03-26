from backend.app.normalization.arabic_text import normalize_arabic_text


def test_arabic_numeric_zero_is_preserved() -> None:
    assert normalize_arabic_text("٪05") == "50٪"
    assert normalize_arabic_text(".03") == "30."
