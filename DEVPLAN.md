# tool-docreader — Development Plan

Document text extraction tool for kiso. Reads PDF, DOCX, XLSX, CSV, and plain text files from the session workspace.

## Architecture

```
stdin (JSON) → run.py → dispatch action → format reader → stdout (text)
```

- **Entry point**: `run.py` reads JSON from stdin, dispatches to action handler
- **Actions**: `read` (default), `info`, `list`
- **Format readers**: `_read_pdf`, `_read_docx`, `_read_xlsx`, `_read_csv`, `_read_text`
- **Security**: path traversal guard (resolved path must be under workspace)
- **Limits**: output truncated at 100K chars

## Capabilities

| Action | Description | Required Args | Output | Status |
|--------|-------------|---------------|--------|--------|
| read | Extract text from file | file_path | Extracted text | Done |
| info | File metadata | file_path | Size, pages/sheets | Done |
| list | List uploads/ files | none | File listing with sizes | Done |

## Dependencies

- `pypdf>=4.0` — PDF text extraction
- `python-docx>=1.1` — DOCX paragraph extraction
- `openpyxl>=3.1` — XLSX sheet/cell reading
- stdlib `csv` — CSV parsing

---

## M1 — Core implementation ✅

Initial implementation of all three actions and five format readers.

- [x] Project structure: kiso.toml, pyproject.toml, run.py, deps.sh, README, LICENSE
- [x] `read` action: PDF (with page ranges), DOCX, XLSX, CSV, plain text
- [x] `info` action: file metadata (size, format, pages/sheets/rows)
- [x] `list` action: enumerate uploads/ directory
- [x] Path traversal guard
- [x] Output truncation (100K chars)
- [x] Unknown extension heuristic (85% printable ASCII)

## M2 — Unit tests ✅

- [x] Test `do_read` for each format: PDF, DOCX, XLSX, CSV, plain text
- [x] Test `do_read` with page ranges for PDF (mocked PdfReader)
- [x] Test `do_info` for each format (PDF pages, XLSX sheets, CSV rows)
- [x] Test `do_list` with files, empty directory, and missing uploads/
- [x] Test path traversal guard (rejected with ValueError)
- [x] Test output truncation on large file
- [x] Test unknown extension heuristic (text and binary)
- [x] Test missing file_path error
- [x] Test unsupported format error
- [x] Functional tests: stdin/stdout subprocess contract (list, read, missing file)
- 35 tests, all passing

## M3 — Integration with kiso registry ✅

- [x] docreader already present in core registry.json (added during M761)
- [x] Repo pushed to git@github.com:kiso-run/tool-docreader.git
- [ ] Verify `kiso tool install docreader` works end-to-end (needs live test on VPS)

## M4 — Smart truncation for large files

**Problem:** When a file exceeds `_MAX_OUTPUT_CHARS` (100K), the output is cut mid-text with a generic `... (truncated at 100000 characters)` marker. The planner gets no structural information about what was omitted or how to access the rest.

**Solution:** Each format reader produces a structured header + truncates at semantic boundaries, with actionable continuation hints.

### PDF
- [x] Header: `Document: {name} ({total_pages} pages)`
- [x] When truncated: cut at page boundary, append `Showing pages 1-{last_shown} of {total_pages}. Use pages="{next_start}-{next_end}" to read more.`
- [x] Always show page count even when not truncated

### CSV
- [x] Header: `Dataset: {name} ({total_rows} rows, {n_cols} columns)\nColumns: {col_names}`
- [x] When truncated: cut at row boundary, append `Showing rows 1-{last_shown} of {total_rows}. Use search(query) to find specific data.`
- [x] Always show row count and column names even when not truncated

### XLSX
- [x] Header: `Workbook: {name} ({n_sheets} sheets: {sheet_names})`
- [x] Per-sheet: show row count in section header. When truncated mid-sheet: cut at row boundary, note truncation
- [x] Continuation hint: `Use search(query) to find specific data across sheets.`

### DOCX / Plain text
- [x] Header: `Document: {name} (~{total_chars} chars)`
- [x] When truncated: cut at paragraph/line boundary, append `Showing first {shown_chars} of {total_chars} chars. Use exec tasks (head, grep) for specific sections.`

### Implementation
- [x] Each reader handles its own truncation inline (no separate `_header_*()` helpers needed — simpler)
- [x] Text reader uses `rfind("\n")` for line-boundary truncation; DOCX iterates paragraphs; PDF iterates pages; CSV/XLSX iterate rows
- [x] `do_read()` delegates entirely to readers — no generic post-hoc chop
- [x] `_MAX_OUTPUT_CHARS` reduced from 100K → 50K

### Tests
- [x] PDF: small file no truncation; large file truncates at page boundary with continuation hint; correct page numbers
- [x] CSV: small file no truncation; large file truncates at row boundary with hint
- [x] XLSX: small file no truncation; large file truncates mid-sheet with hint
- [x] DOCX: small file no truncation; large file truncates at paragraph boundary
- [x] Plain text: small file no truncation; large file truncates at line boundary

### Validation
- [x] `uv run pytest tests/ -q` — 45 passed
- [ ] Manual test: read a 100+ page PDF → output shows header + first N pages + continuation hint (needs VPS)

## Known Issues

- pypdf text extraction quality varies by PDF — scanned PDFs produce empty text (no OCR)
- XLSX read_only mode may not evaluate formulas (data_only=True helps but not always)
