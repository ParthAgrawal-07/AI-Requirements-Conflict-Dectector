# Document Ingestion & Extraction Module Design (Sprint 0)

## 1. Purpose of the Ingestion Module
The ingestion module is responsible for reading source Software Requirements Specifications (SRS) documents and parsing them into a structured format. It performs the initial extraction of text and basic segmentation to isolate individual requirements before they are sent to the embedding and classification stages.

## 2. PDF Parsing Decision (PyMuPDF)
We selected `PyMuPDF` (`fitz`) because our expected SRS documents are born-digital, structured PDFs. PyMuPDF is extremely fast, lightweight, and handles text extraction across pages reliably without the heavy overhead or dependencies of OCR libraries (which we explicitly avoided in Sprint 0).

## 3. DOCX Parsing Decision (python-docx)
We selected `python-docx` as the standard for parsing Microsoft Word documents. It is a mature, robust library specifically designed for reading the `.docx` XML structure, allowing us to accurately iterate through paragraphs without parsing binary formats.

## 3a. Alternatives Considered

| Library | Format | Why not chosen (for Sprint 0–1) |
|---|---|---|
| **PyMuPDF** ✅ | PDF | Chosen — fastest pure text extraction, single wheel, page-level API, also gives block/font info we can use for heading detection later. AGPL licence is fine for a course project. |
| pdfplumber / pdfminer.six | PDF | Better table extraction, but ~10–20× slower and noisier line output. Revisit only if PDF tables become a problem. |
| pypdf | PDF | Pure Python and permissive licence, but weaker text ordering and spacing on real-world PDFs. |
| unstructured / docling | PDF + DOCX | Layout-aware and handle both formats, but pull in heavy ML dependencies (torch, layout models) — too much for our Docker image and CI time. |
| **python-docx** ✅ | DOCX | Chosen — de-facto standard, exposes paragraph styles (headings) and tables in reading order (`iter_inner_content`, requires python-docx ≥ 1.0). |
| docx2txt / mammoth | DOCX | Flatten to text/HTML and lose style + table structure we need for headings and ID tables. |

## 4. Supported Formats
- `.pdf` (born-digital)
- `.docx` (Office Open XML)

## 5. Unsupported Formats
- `.doc` (older binary format)
- `.txt`, `.odt`, and other undocumented formats
Any attempt to ingest these will raise a clear `ValueError` exception.

### Error handling (FR-02)
Supported-format files that cannot be read raise `DocumentParseError` (a `ValueError` subclass), so the upload endpoint can catch one exception type and show the user a message:
- corrupted / not-really-a-PDF or DOCX file
- password-protected PDF
- no extractable text at all (e.g. scanned, image-only PDF — we do no OCR)

## 6. RawSegment Schema
The intermediate model representing extracted chunks (before requirement segmentation):
- `text` (str)
- `source_document` (str)
- `page_or_paragraph` (int)
- `location_type` (`"page"` | `"paragraph"`)
- `section_heading` (str | None)
- `order_index` (int)

*Note: For PDFs, `page_or_paragraph` is the page number. For DOCX it is the 1-based body-block index, where each paragraph and each table row counts as one block. `location_type` says which, so the schema stays format-agnostic while locations remain human-readable.*

DOCX specifics: tables are read row by row (cells joined with ` | `) because SRS documents often list requirements in `ID | Description` tables. Heading-styled paragraphs are not emitted as segments; they become the `section_heading` of the segments that follow.

## 7. Requirement Schema
The final output model representing a segmented requirement:
- `id` (str) — the source ID, or a deterministic `UNKNOWN-…` fallback
- `source_req_id` (str | None) — the ID exactly as written, or None (maps to `requirements.source_req_id` in `engineering/data-model.md`)
- `raw_text` (str)
- `source_document` (str)
- `location` (str) — e.g. `"page 3"` or `"paragraph 12"`
- `section_heading` (str | None)
- `extracted_at` (datetime)

## 8. Parser Abstraction
We define a generic `Parser` abstract base class with a `parse(file_path: str) -> List[RawSegment]` method. Both `PDFParser` and `DOCXParser` implement this, ensuring a uniform interface for the rest of the pipeline.

## 9. Basic Segmentation Approach
In Sprint 0, segmentation is a simple, deterministic proof-of-concept. It iterates through the text of each segment line-by-line and uses a regex to look for a requirement ID **at the start of the line** (after optional whitespace, bullet or bracket): `REQ-001`, `FR-1.2.3`, `NFR-01`, `DR-03`. IDs that appear mid-sentence are treated as cross-references ("conflicts with FR-1"), not as the line's own ID. If no ID is found, it falls back to a deterministic unknown ID format: `UNKNOWN-<page/para_num>-<index>`.

## 10. Known Sprint 0 Limitations
- Segmentation is extremely basic (regex line matching) and NOT production-ready.
- Layout reconstruction for PDFs (e.g., detecting multi-column layouts, tables) is not implemented.
- Section headings are detected for DOCX (via paragraph styles) but not yet for PDFs.
- A requirement that wraps over several PDF lines becomes several requirements (one per line); the continuation lines get `UNKNOWN-…` IDs.
- Headings, intro text, and page headers/footers in PDFs also become `UNKNOWN-…` requirements.

## 11. What will be improved in Sprint 1
- Production-quality segmentation (T10: spaCy sentence splitting + REQ-ID preservation), including merging wrapped continuation lines into the preceding requirement.
- Better parsing of structured lists and headings as context.
- Advanced layout heuristics for PDF extraction.
