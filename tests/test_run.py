"""Unit tests for tool-docreader (M2)."""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Import directly from run.py (pythonpath = ["."])
from run import (
    do_list, do_info, do_read,
    _resolve_path, _parse_page_ranges, _format_size, _is_likely_text,
    _MAX_OUTPUT_CHARS,
)


# ---------------------------------------------------------------------------
# Fixtures — create real small files for each format
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path):
    """Create a workspace with uploads/ directory."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    return tmp_path


@pytest.fixture
def txt_file(workspace):
    """Create a plain text file."""
    f = workspace / "uploads" / "hello.txt"
    f.write_text("Hello, world!\nSecond line.")
    return f


@pytest.fixture
def csv_file(workspace):
    """Create a CSV file."""
    f = workspace / "uploads" / "data.csv"
    with open(f, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["name", "age", "city"])
        writer.writerow(["Alice", "30", "Rome"])
        writer.writerow(["Bob", "25", "Milan"])
    return f


@pytest.fixture
def pdf_file(workspace):
    """Create a minimal PDF file using pypdf."""
    from pypdf import PdfWriter
    f = workspace / "uploads" / "doc.pdf"
    writer = PdfWriter()
    # Add 3 pages with text
    for i in range(3):
        writer.add_blank_page(width=200, height=200)
    # pypdf blank pages have no text — we'll test the "no text" path
    writer.write(str(f))
    return f


@pytest.fixture
def pdf_with_text(workspace):
    """Create a PDF with actual text content using reportlab-free method."""
    # We use pypdf's add_blank_page — text extraction returns empty for blank pages.
    # For a real text PDF we'll mock the reader in specific tests.
    return None  # See mock-based tests below


@pytest.fixture
def docx_file(workspace):
    """Create a minimal DOCX file."""
    from docx import Document
    f = workspace / "uploads" / "report.docx"
    doc = Document()
    doc.add_paragraph("First paragraph of the report.")
    doc.add_paragraph("Second paragraph with details.")
    doc.save(str(f))
    return f


@pytest.fixture
def xlsx_file(workspace):
    """Create a minimal XLSX file."""
    from openpyxl import Workbook
    f = workspace / "uploads" / "sheet.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["Name", "Score"])
    ws.append(["Alice", 95])
    ws.append(["Bob", 87])
    wb.save(str(f))
    return f


# ---------------------------------------------------------------------------
# do_list
# ---------------------------------------------------------------------------


class TestDoList:
    def test_list_with_files(self, workspace, txt_file, csv_file):
        result = do_list(str(workspace))
        assert "Files in uploads/ (2):" in result
        assert "hello.txt" in result
        assert "data.csv" in result

    def test_list_empty_directory(self, workspace):
        result = do_list(str(workspace))
        assert "empty" in result.lower()

    def test_list_no_uploads_dir(self, tmp_path):
        result = do_list(str(tmp_path))
        assert "No uploads/" in result


# ---------------------------------------------------------------------------
# do_info
# ---------------------------------------------------------------------------


class TestDoInfo:
    def test_info_txt(self, workspace, txt_file):
        result = do_info(str(workspace), {"file_path": "uploads/hello.txt"})
        assert "hello.txt" in result
        assert ".txt" in result
        assert "B" in result or "KB" in result

    def test_info_csv(self, workspace, csv_file):
        result = do_info(str(workspace), {"file_path": "uploads/data.csv"})
        assert "Rows:" in result
        assert "3" in result  # header + 2 data rows

    def test_info_pdf(self, workspace, pdf_file):
        result = do_info(str(workspace), {"file_path": "uploads/doc.pdf"})
        assert "Pages: 3" in result

    def test_info_xlsx(self, workspace, xlsx_file):
        result = do_info(str(workspace), {"file_path": "uploads/sheet.xlsx"})
        assert "Sheets:" in result
        assert "Data" in result

    def test_info_missing_file(self, workspace):
        with pytest.raises(FileNotFoundError):
            do_info(str(workspace), {"file_path": "uploads/nope.pdf"})


# ---------------------------------------------------------------------------
# do_read
# ---------------------------------------------------------------------------


class TestDoRead:
    def test_read_txt(self, workspace, txt_file):
        result = do_read(str(workspace), {"file_path": "uploads/hello.txt"})
        assert "Hello, world!" in result
        assert "Second line." in result

    def test_read_csv(self, workspace, csv_file):
        result = do_read(str(workspace), {"file_path": "uploads/data.csv"})
        assert "Alice" in result
        assert "Bob" in result
        assert "Rome" in result

    def test_read_docx(self, workspace, docx_file):
        result = do_read(str(workspace), {"file_path": "uploads/report.docx"})
        assert "First paragraph" in result
        assert "Second paragraph" in result

    def test_read_xlsx(self, workspace, xlsx_file):
        result = do_read(str(workspace), {"file_path": "uploads/sheet.xlsx"})
        assert "Alice" in result
        assert "95" in result
        assert "Bob" in result
        assert "Sheet: Data" in result

    def test_read_pdf_blank_pages(self, workspace, pdf_file):
        result = do_read(str(workspace), {"file_path": "uploads/doc.pdf"})
        assert "no extractable text" in result.lower()

    def test_read_pdf_with_text(self, workspace, pdf_file):
        """Test PDF reading with mocked text extraction."""
        from unittest.mock import MagicMock
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Page content here"

        with patch("pypdf.PdfReader") as MockReader:
            MockReader.return_value.pages = [mock_page, mock_page]
            result = do_read(str(workspace), {"file_path": "uploads/doc.pdf"})
        assert "Page content here" in result
        assert "Page 1" in result
        assert "Page 2" in result

    def test_read_pdf_page_ranges(self, workspace, pdf_file):
        """Test PDF with page range argument."""
        from unittest.mock import MagicMock
        pages = []
        for i in range(5):
            p = MagicMock()
            p.extract_text.return_value = f"Content of page {i+1}"
            pages.append(p)

        with patch("pypdf.PdfReader") as MockReader:
            MockReader.return_value.pages = pages
            result = do_read(str(workspace), {
                "file_path": "uploads/doc.pdf",
                "pages": "2-3",
            })
        assert "Content of page 2" in result
        assert "Content of page 3" in result
        assert "Content of page 1" not in result
        assert "Content of page 4" not in result

    def test_read_unsupported_format(self, workspace):
        f = workspace / "uploads" / "data.xyz"
        f.write_bytes(b"\x00\x01\x02\x03" * 200)  # binary junk
        result = do_read(str(workspace), {"file_path": "uploads/data.xyz"})
        assert "Unsupported" in result

    def test_read_unknown_extension_text_heuristic(self, workspace):
        f = workspace / "uploads" / "config.env"
        f.write_text("KEY=value\nOTHER=stuff\n")
        result = do_read(str(workspace), {"file_path": "uploads/config.env"})
        assert "KEY=value" in result

    def test_read_missing_file_path(self, workspace):
        with pytest.raises(ValueError, match="file_path"):
            do_read(str(workspace), {})


# ---------------------------------------------------------------------------
# Output truncation
# ---------------------------------------------------------------------------


class TestTruncation:
    def test_large_file_truncated(self, workspace):
        f = workspace / "uploads" / "big.txt"
        f.write_text("x" * (_MAX_OUTPUT_CHARS + 10000))
        result = do_read(str(workspace), {"file_path": "uploads/big.txt"})
        assert len(result) < _MAX_OUTPUT_CHARS + 200  # room for truncation message
        assert "truncated" in result.lower()


# ---------------------------------------------------------------------------
# Path traversal guard
# ---------------------------------------------------------------------------


class TestPathTraversal:
    def test_traversal_rejected(self, workspace):
        with pytest.raises(ValueError, match="traversal"):
            _resolve_path(str(workspace), {"file_path": "../../etc/passwd"})

    def test_valid_path_accepted(self, workspace, txt_file):
        result = _resolve_path(str(workspace), {"file_path": "uploads/hello.txt"})
        assert result.name == "hello.txt"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestParsePageRanges:
    def test_single_page(self):
        assert _parse_page_ranges("3", 10) == [2]  # zero-based

    def test_range(self):
        assert _parse_page_ranges("2-4", 10) == [1, 2, 3]

    def test_mixed(self):
        assert _parse_page_ranges("1,3-5,8", 10) == [0, 2, 3, 4, 7]

    def test_out_of_bounds_clamped(self):
        result = _parse_page_ranges("1-100", 5)
        assert result == [0, 1, 2, 3, 4]

    def test_deduplication(self):
        result = _parse_page_ranges("1-3,2-4", 10)
        assert result == [0, 1, 2, 3]  # no duplicates


class TestFormatSize:
    def test_bytes(self):
        assert _format_size(500) == "500 B"

    def test_kilobytes(self):
        assert "KB" in _format_size(2048)

    def test_megabytes(self):
        assert "MB" in _format_size(5 * 1024 * 1024)


class TestIsLikelyText:
    def test_text_file(self, tmp_path):
        f = tmp_path / "readme.nfo"
        f.write_text("This is plain text content.")
        assert _is_likely_text(f) is True

    def test_binary_file(self, tmp_path):
        f = tmp_path / "image.bin"
        f.write_bytes(bytes(range(256)) * 4)
        assert _is_likely_text(f) is False

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty"
        f.write_bytes(b"")
        assert _is_likely_text(f) is False


# ---------------------------------------------------------------------------
# Functional: stdin/stdout contract
# ---------------------------------------------------------------------------


class TestFunctional:
    def test_list_via_stdin(self, workspace, txt_file):
        """Full subprocess: JSON stdin → stdout."""
        input_data = json.dumps({
            "args": {"action": "list"},
            "workspace": str(workspace),
        })
        result = subprocess.run(
            [sys.executable, "run.py"],
            input=input_data, capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0
        assert "hello.txt" in result.stdout

    def test_read_via_stdin(self, workspace, txt_file):
        input_data = json.dumps({
            "args": {"action": "read", "file_path": "uploads/hello.txt"},
            "workspace": str(workspace),
        })
        result = subprocess.run(
            [sys.executable, "run.py"],
            input=input_data, capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0
        assert "Hello, world!" in result.stdout

    def test_missing_file_exits_1(self, workspace):
        input_data = json.dumps({
            "args": {"action": "read", "file_path": "uploads/nope.txt"},
            "workspace": str(workspace),
        })
        result = subprocess.run(
            [sys.executable, "run.py"],
            input=input_data, capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 1
        assert "not found" in result.stderr.lower() or "not found" in result.stdout.lower()
