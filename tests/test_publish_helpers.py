from halo_cli.publish import _find_first_key


def test_find_first_key_in_nested_dict():
    obj = {"a": {"b": {"k": "v"}}}
    assert _find_first_key(obj, "k") == "v"


def test_find_first_key_in_list():
    obj = [{"x": 1}, {"k": 2}]
    assert _find_first_key(obj, "k") == 2

