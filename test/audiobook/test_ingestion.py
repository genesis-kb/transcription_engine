"""Tests for app.services.audiobook.ingestion — Groups 5-6."""

import pytest
from pathlib import Path

from app.services.audiobook.ingestion import parse_file, group_series


# ── Group 5: parse_file ──────────────────────────────────────────────

class TestParseFile:
    def test_valid_single_article(self, tmp_dir):
        f = tmp_dir / "article.txt"
        f.write_text("---\ntype: single_article\ntitle: Test Article\n---\nBody text here.")
        result = parse_file(f)
        assert result is not None
        assert result.input_type == "single_article"
        assert result.title == "Test Article"
        assert result.body == "Body text here."

    def test_valid_series(self, tmp_dir):
        f = tmp_dir / "ch1.txt"
        f.write_text(
            "---\ntype: series\nseries_slug: btc-guide\n"
            "series_title: Bitcoin Guide\nsequence_number: 1\ntitle: Intro\n---\nHello."
        )
        result = parse_file(f)
        assert result is not None
        assert result.input_type == "series"
        assert result.series_slug == "btc-guide"
        assert result.sequence_number == 1

    def test_no_frontmatter_treated_as_single(self, tmp_dir):
        f = tmp_dir / "my_article.txt"
        f.write_text("Just plain text here.")
        result = parse_file(f)
        assert result is not None
        assert result.input_type == "single_article"
        # Title derived from filename
        assert "My Article" in result.title

    def test_empty_body_returns_none(self, tmp_dir):
        f = tmp_dir / "empty.txt"
        f.write_text("---\ntitle: Empty\n---\n")
        assert parse_file(f) is None

    def test_invalid_yaml_returns_none(self, tmp_dir):
        f = tmp_dir / "bad.txt"
        f.write_text("---\n: [invalid yaml\n---\nBody.")
        assert parse_file(f) is None

    def test_series_missing_slug_returns_none(self, tmp_dir):
        f = tmp_dir / "no_slug.txt"
        f.write_text("---\ntype: series\nsequence_number: 1\nseries_title: X\ntitle: X\n---\nBody.")
        assert parse_file(f) is None

    def test_series_missing_sequence_returns_none(self, tmp_dir):
        f = tmp_dir / "no_seq.txt"
        f.write_text("---\ntype: series\nseries_slug: x\nseries_title: X\ntitle: X\n---\nBody.")
        assert parse_file(f) is None

    def test_series_missing_series_title_returns_none(self, tmp_dir):
        f = tmp_dir / "no_st.txt"
        f.write_text("---\ntype: series\nseries_slug: x\nsequence_number: 1\ntitle: X\n---\nBody.")
        assert parse_file(f) is None

    def test_unknown_type_returns_none(self, tmp_dir):
        f = tmp_dir / "unknown.txt"
        f.write_text("---\ntype: podcast\ntitle: X\n---\nBody.")
        assert parse_file(f) is None

    def test_tags_as_string_parsed_as_list(self, tmp_dir):
        f = tmp_dir / "tag_str.txt"
        f.write_text("---\ntitle: T\ntags: bitcoin\n---\nBody.")
        result = parse_file(f)
        assert result.tags == ["bitcoin"]

    def test_tags_as_list(self, tmp_dir):
        f = tmp_dir / "tag_list.txt"
        f.write_text("---\ntitle: T\ntags: [a, b]\n---\nBody.")
        result = parse_file(f)
        assert result.tags == ["a", "b"]

    def test_non_integer_sequence_returns_none(self, tmp_dir):
        f = tmp_dir / "bad_seq.txt"
        f.write_text(
            "---\ntype: series\nseries_slug: x\n"
            "series_title: X\nsequence_number: abc\ntitle: X\n---\nBody."
        )
        assert parse_file(f) is None


# ── Group 6: group_series ────────────────────────────────────────────

class TestGroupSeries:
    def _make_input(self, slug, seq, input_type="series"):
        from app.services.audiobook.ingestion import InputFile
        return InputFile(
            filepath=Path(f"fake_{seq}.txt"),
            input_type=input_type,
            title=f"Part {seq}",
            body="text",
            series_slug=slug if input_type == "series" else None,
            sequence_number=seq,
        )

    def test_groups_by_slug(self):
        inputs = [self._make_input("btc", 1), self._make_input("btc", 2)]
        groups = group_series(inputs)
        assert "btc" in groups
        assert len(groups["btc"]) == 2

    def test_sorted_by_sequence_number(self):
        inputs = [self._make_input("btc", 3), self._make_input("btc", 1)]
        groups = group_series(inputs)
        assert groups["btc"][0].sequence_number == 1

    def test_single_articles_excluded(self):
        inputs = [self._make_input("btc", 1, "single_article")]
        groups = group_series(inputs)
        assert len(groups) == 0

    def test_two_different_slugs(self):
        inputs = [self._make_input("btc", 1), self._make_input("eth", 1)]
        groups = group_series(inputs)
        assert len(groups) == 2
