from apex.safety.validators import extract_first_json_object


def test_extract_first_json_object_basic():
    s = "Here is your JSON: {\"a\": 1, \"b\": {\"c\": 2}} trailing text"
    out = extract_first_json_object(s)
    assert out == "{\"a\": 1, \"b\": {\"c\": 2}}"


def test_extract_first_json_object_ignores_braces_in_strings():
    s = 'prefix {"a":"{ not real }", "b": 2} suffix'
    out = extract_first_json_object(s)
    assert out == '{"a":"{ not real }", "b": 2}'

