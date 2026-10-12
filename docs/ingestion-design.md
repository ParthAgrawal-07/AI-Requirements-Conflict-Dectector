# Document Ingestion & Extraction Module Design (Sprints 0–1)

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
- `is_list_item` (bool) — DOCX list paragraph (Word bullets are formatting, not text)
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
- `order_index` (int) — position in the document
- `needs_review` (bool) and `review_reasons` (tuple[str, ...]) — see §9.3
- `extracted_at` (datetime)

`ingest_document()` returns a `SegmentationResult`: the requirements plus `excluded` — every passage dropped as non-requirement text, with a reason (`toc`, `fragment`, `non_requirement_section`), so exclusions can be audited.

## 8. Parser Abstraction
We define a generic `Parser` abstract base class with a `parse(file_path: str) -> List[RawSegment]` method. Both `PDFParser` and `DOCXParser` implement this, ensuring a uniform interface for the rest of the pipeline.

## 9. Segmentation (Sprint 1, US-02 / T10)

Implemented in `segmentation/segmenter.py`; patterns in `segmentation/rules.py`.

### 9.1 Layout clean-up (PDF parser)
- Text is read per PyMuPDF block, with blocks separated by a blank line, so a paragraph break can be told apart from a wrapped line.
- **Headers/footers:** a block in the top/bottom 10% of the page is dropped if it is a bare page number (`3`, `Page 3 of 10`, `- 3 -`) or if the same text (digits ignored) is in the margin of at least half the pages. Blocks containing a requirement ID or `shall`/`must` are never dropped.

### 9.2 Grouping lines into units
- A line starting with a requirement ID (`REQ-001`, `FR-1.2.3`, `NFR-01`, `DR-03`, `SR-`, `UR-`, `BR-`, `SYS-`) starts a new unit. IDs mid-sentence are cross-references, not the line's own ID.
- Wrapped lines are re-joined (`real-` + `time` → `real-time`).
- A new paragraph starts a new unit unless the current one is still open:
  - it ends with `:` (a list follows);
  - it is a bare ID (ID and text in separate blocks or cells);
  - it was cut off by a page break mid-sentence.
- **Lists:** items after a lead-in (`…the following channels:`) stay with it as sub-items; an item that is itself a `shall`/`must` statement stands alone.
- **Headings** (numbered like `3.2 Functional Requirements`, or short Title Case / UPPER CASE lines; DOCX heading styles) are not requirements; they become `section_heading` of what follows. Figure/table captions are not headings.
- **Table of contents:** lines with dot leaders, DOCX `TOC n` paragraphs, and entries following a `Contents` title are excluded.

### 9.3 Classification
- A unit **with an ID** is one requirement and keeps its ID (DR-03). It is flagged for review if:
  - the ID has no text;
  - it holds several `shall`/`must` sentences (possibly several requirements);
  - it is over 1000 characters.
- A unit **without an ID** is split into sentences with spaCy's rule-based `sentencizer` (`spacy.blank("en")`, so no model download in Docker/CI). Each sentence with a modal verb starts a new requirement, and other sentences stay attached as context. Chunks are slices of the original text, so the wording is preserved (FR-04).
- Text without an ID:
  - `shall`/`must`: requirement. Flagged if it sits in an intro/glossary-type section.
  - `should`/`will`/`can`/`may`: requirement, flagged ("weaker modal verb").
  - no modal: excluded if it is a fragment (under 4 words, no punctuation, e.g. a table header) or sits under a non-requirement heading (Introduction, Purpose, Scope, Glossary, References, …). Otherwise it is kept and flagged.
- Duplicate source IDs in one document are all flagged (duplicate IDs are themselves a finding).
- Requirements without a source ID get `UNKNOWN-<page/para>-<n>`.

Design rule: **when unsure, keep and flag** (US-02: low-confidence segmentation is surfaced for manual review, not silently dropped).

## 10. Integration with orchestration
Storing results and running the Celery task belong to Role 5 (Parth): `app.services.processing.process_document` (PR #7) calls `ingest(path)` and saves each returned `Requirement` (`id`, `raw_text`, `location`).

Handled by the pipeline, which `process_document` relies on:
- every failure is a `ValueError` (`DocumentParseError` for corrupt, encrypted or text-less files);
- an empty list means no requirements were found;
- fallback IDs look like `UNKNOWN-…`, which never match `REQUIREMENT_ID_PATTERN`.

**Follow-up after PR #7 merges:** add migration `0003` with `requirements.section_heading`, `needs_review` and `review_reason`, and have `process_document` save `section_heading`, `needs_review` and `review_reasons` (joined with "; "). Until then, review flags are computed but not stored.

## 11. Known Limitations
- Multi-column PDFs: blocks are read top-to-bottom, so two columns can interleave.
- Tables in PDFs are read as text blocks; DOCX tables are read row by row (`cell | cell | cell`), including non-ID columns such as priority.
- Heading detection in PDFs is text-based (numbering, case), not font-based.
- No OCR: scanned PDFs fail with a clear message.
- `.txt` and ReqIF (listed in US-01) are not supported yet.
- FR-06 (user corrects segmentation errors) is not implemented. The `needs_review` flags are what that UI should show first, once they are stored (see §10).
