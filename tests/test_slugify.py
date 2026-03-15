from halo_cli.client import slugify_dns_label


def test_slugify_dns_label_basic():
    assert slugify_dns_label("Hello World") == "hello-world"


def test_slugify_dns_label_strips_and_lowercases():
    assert slugify_dns_label("  Hello  ") == "hello"


def test_slugify_dns_label_fallback_when_empty():
    assert slugify_dns_label("!!!", fallback="post") == "post"


def test_slugify_dns_label_max_length():
    s = "a" * 100
    assert len(slugify_dns_label(s)) <= 63

