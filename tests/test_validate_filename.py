"""
test_validate_filename.py — unit tests for validate_reports._parse_pdf_filename().

Covers:
- Standard format: YYYYMMDD ResilienceScanReport (Company - Person).pdf
- Legacy format: YYYYMMDD ResilienceReport (Company - Person).pdf
- Company name containing a hyphen (rsplit " - " takes rightmost)
- Multi-word person name
- Missing parentheses → None
- Missing " - " separator inside parens → None
- Empty string → None
- Wrong file extension → None
- Case-insensitive .PDF extension
- Leading/trailing whitespace stripped from company and person
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validate_reports import _parse_pdf_filename  # noqa: E402  # type: ignore[import]


def test_standard_format():
    fname = "20240115 ResilienceScanReport (Acme Corp - Alice Smith).pdf"
    assert _parse_pdf_filename(fname) == ("Acme Corp", "Alice Smith")


def test_legacy_format():
    fname = "20230601 ResilienceReport (Windesheim - Jan de Vries).pdf"
    assert _parse_pdf_filename(fname) == ("Windesheim", "Jan de Vries")


def test_company_with_hyphen():
    """rsplit(' - ', 1) keeps the rightmost split, so company may contain hyphens."""
    fname = "20240101 ResilienceScanReport (Alpha-Beta Corp - Bob Jones).pdf"
    assert _parse_pdf_filename(fname) == ("Alpha-Beta Corp", "Bob Jones")


def test_multiword_person_name():
    fname = "20240101 ResilienceScanReport (Acme - Maria van den Berg).pdf"
    assert _parse_pdf_filename(fname) == ("Acme", "Maria van den Berg")


def test_missing_parens_returns_none():
    fname = "20240101 ResilienceScanReport Acme Corp - Alice Smith.pdf"
    assert _parse_pdf_filename(fname) is None


def test_missing_separator_returns_none():
    """Content inside parens with no ' - ' → None."""
    fname = "20240101 ResilienceScanReport (Acme Corp Alice Smith).pdf"
    assert _parse_pdf_filename(fname) is None


def test_empty_string_returns_none():
    assert _parse_pdf_filename("") is None


def test_wrong_extension_returns_none():
    fname = "20240101 ResilienceScanReport (Acme Corp - Alice Smith).docx"
    assert _parse_pdf_filename(fname) is None


def test_case_insensitive_extension():
    """.PDF (uppercase) is accepted because the regex uses re.IGNORECASE."""
    fname = "20240101 ResilienceScanReport (Acme Corp - Alice Smith).PDF"
    assert _parse_pdf_filename(fname) == ("Acme Corp", "Alice Smith")


def test_strips_whitespace():
    """Leading/trailing whitespace inside parens is stripped."""
    fname = "20240101 ResilienceScanReport ( Acme Corp  -  Alice Smith ).pdf"
    result = _parse_pdf_filename(fname)
    assert result is not None
    company, person = result
    assert company == "Acme Corp"
    assert person == "Alice Smith"


def test_single_word_company_and_person():
    fname = "20240101 ResilienceScanReport (Acme - Bob).pdf"
    assert _parse_pdf_filename(fname) == ("Acme", "Bob")
