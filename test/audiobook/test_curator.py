"""Tests for app.services.audiobook.curator — Group 13 (_slugify)."""

from app.services.audiobook.curator import _slugify


class TestSlugify:
    def test_normal_title(self):
        assert _slugify("Bitcoin Basics") == "bitcoin-basics"

    def test_special_chars_stripped(self):
        assert _slugify("Hello, World!") == "hello-world"

    def test_multiple_spaces_collapsed(self):
        assert _slugify("a  b") == "a-b"

    def test_empty_string(self):
        assert _slugify("") == "untitled"

    def test_leading_trailing_hyphens_stripped(self):
        assert _slugify("--hello--") == "hello"
