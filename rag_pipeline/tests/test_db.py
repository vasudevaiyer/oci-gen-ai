from backend.app.db import _load_json_list, _load_json_object


def test_load_json_helpers_accept_valid_json_and_python_literal_fallbacks() -> None:
    assert _load_json_list('["en", "ar"]') == ["en", "ar"]
    assert _load_json_list("['en', 'ar']") == ["en", "ar"]
    assert _load_json_object('{"a": 1}') == {"a": 1}
    assert _load_json_object("{'a': 1}") == {"a": 1}


def test_load_json_helpers_fall_back_for_invalid_or_wrong_shapes() -> None:
    assert _load_json_list('not-json') == []
    assert _load_json_list('{"a": 1}') == []
    assert _load_json_object('not-json') == {}
    assert _load_json_object('[1, 2, 3]') == {}
