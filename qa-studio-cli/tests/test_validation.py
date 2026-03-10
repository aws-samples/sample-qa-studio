"""Tests for client-side validation."""

import pytest

from qa_studio_cli.validation import (
    validate_journey_description,
    validate_url,
    validate_title,
    validate_region,
    VALID_REGIONS,
)


class TestJourneyValidation:
    """Tests for journey description validation."""

    def test_valid_journey(self):
        journey = "Navigate to the login page, click the sign in button, enter username and password, click submit button, verify dashboard is visible"
        is_valid, errors = validate_journey_description(journey)
        assert is_valid
        assert len(errors) == 0

    def test_empty_journey(self):
        is_valid, errors = validate_journey_description("")
        assert not is_valid
        assert "required" in errors[0].lower()

    def test_journey_too_short(self):
        journey = "Click button"
        is_valid, errors = validate_journey_description(journey)
        assert not is_valid
        assert any("50 characters" in e for e in errors)

    def test_journey_too_long(self):
        journey = "x" * 2001
        is_valid, errors = validate_journey_description(journey)
        assert not is_valid
        assert any("2000 characters" in e for e in errors)

    def test_journey_too_few_words(self):
        journey = "a b c d e f g h i"  # 9 words
        is_valid, errors = validate_journey_description(journey)
        assert not is_valid
        assert any("10 words" in e for e in errors)

    def test_journey_missing_action_words(self):
        journey = "The user goes to the page and does something with the form and sees the result"
        is_valid, errors = validate_journey_description(journey)
        assert not is_valid
        assert any("action" in e.lower() for e in errors)


class TestUrlValidation:
    """Tests for URL validation."""

    def test_valid_url(self):
        is_valid, errors = validate_url("https://example.com")
        assert is_valid
        assert len(errors) == 0

    def test_valid_url_with_path(self):
        is_valid, errors = validate_url("https://example.com/path/to/page")
        assert is_valid
        assert len(errors) == 0

    def test_empty_url(self):
        is_valid, errors = validate_url("")
        assert not is_valid
        assert "required" in errors[0].lower()

    def test_invalid_url_no_protocol(self):
        is_valid, errors = validate_url("example.com")
        assert not is_valid
        assert "protocol" in errors[0].lower()

    def test_invalid_url_format(self):
        is_valid, errors = validate_url("not a url")
        assert not is_valid


class TestTitleValidation:
    """Tests for title validation."""

    def test_valid_title(self):
        is_valid, errors = validate_title("My Test")
        assert is_valid
        assert len(errors) == 0

    def test_empty_title(self):
        is_valid, errors = validate_title("")
        assert not is_valid
        assert "required" in errors[0].lower()

    def test_title_too_short(self):
        is_valid, errors = validate_title("ab")
        assert not is_valid
        assert "3 characters" in errors[0]

    def test_title_too_long(self):
        title = "x" * 101
        is_valid, errors = validate_title(title)
        assert not is_valid
        assert "100 characters" in errors[0]


class TestRegionValidation:
    """Tests for region validation."""

    def test_valid_regions(self):
        for region in VALID_REGIONS:
            is_valid, errors = validate_region(region)
            assert is_valid, f"Region {region} should be valid"
            assert len(errors) == 0

    def test_empty_region(self):
        is_valid, errors = validate_region("")
        assert not is_valid
        assert "required" in errors[0].lower()

    def test_invalid_region(self):
        is_valid, errors = validate_region("invalid-region")
        assert not is_valid
        assert "Invalid region" in errors[0]
        assert all(r in errors[0] for r in VALID_REGIONS)
