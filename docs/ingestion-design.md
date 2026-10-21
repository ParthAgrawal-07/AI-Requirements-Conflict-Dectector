# Document Ingestion & Extraction Module Design (Sprints 0–1, revision 5)

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

A file with no extractable text (e.g. a scanned, image-only PDF; we do no OCR) is not an error. It yields an empty result, which the processing service reports as "no requirements found".

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

`ingest_document()` returns a `SegmentationResult`:
- `requirements`;
- `excluded` — every passage dropped as non-requirement text, with a reason (`toc`, `fragment`, `non_requirement_section`), so exclusions can be audited;
- `sections` — every heading and the verbatim text under it (§9.4).

## 7a. DocumentSection Schema
- `heading` (str | None) — None for text before the first heading
- `body` (str) — the paragraphs under the heading, verbatim, separated by blank lines; requirements and prose alike
- `location` (str) — where the section starts
- `order_index` (int)

Sections feed the `document_sections` table (design update §12.1). The brief drafter reads the introduction and overall description from them (FR-104), and the context pack picks the three most relevant ones for each LLM call (FR-105). Headings with no text of their own (a chapter title directly followed by its first sub-heading) and table-of-contents lines are not sections.

## 8. Parser Abstraction
We define a generic `Parser` abstract base class with a `parse(file_path: str) -> List[RawSegment]` method. Both `PDFParser` and `DOCXParser` implement this, ensuring a uniform interface for the rest of the pipeline.

## 9. Segmentation (Sprint 1, US-02 / T10)

Implemented in `segmentation/segmenter.py`; patterns in `segmentation/rules.py`.

### 9.1 Layout clean-up (PDF parser)
- Text is read per PyMuPDF block, with blocks separated by a blank line, so a paragraph break can be told apart from a wrapped line.
- **Headers/footers:** a block in the top/bottom 10% of the page is dropped if it is a bare page number (`3`, `Page 3 of 10`, `- 3 -`) or if the same text (digits ignored) is in the margin of at least half the pages. Blocks containing a requirement ID or `shall`/`must` are never dropped.

### 9.2 Grouping lines into units
- A line starting with a requirement ID starts a new unit. An ID is an upper-case prefix, optionally in several parts, then `-` or `_`, then a number with optional sub-numbers and an optional one-letter suffix: `REQ-001`, `FR-1.2.3`, `NFR-01`, `UC-07`, `SEC-3`, `PERF_01`, `FR-AUTH-01`, `REQ-SEC-001`, `REQ-001-A`, `UC-1a`. Standard and encoding names that look the same (`ISO-27001`, `UTF-8`, `TLS-1.2`, `IEEE-830`, …) are not IDs, and neither is a number with a longer word glued to it (`SEC-1st`). IDs mid-sentence are cross-references, not the line's own ID.
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
- Requirements without a source ID get `UNKNOWN-<page/para>-<n>` as `id`, and `source_req_id` stays `None`: an item with no printed ID is stored without one, and the fallback is never shown as if it were a source ID (FR-04).

Design rule: **when unsure, keep and flag** (US-02: low-confidence segmentation is surfaced for manual review, not silently dropped).

### 9.4 Sections
While grouping, the segmenter also records sections: a DOCX heading style or a detected heading (§9.2) opens a new section, and every other line that is not part of the table of contents is added to it, verbatim, whether it became a requirement, was flagged or was excluded. A DOCX segment is one paragraph; in a PDF a blank line between blocks separates paragraphs.

## 10. Integration with orchestration
Storing results and running the Celery task belong to Role 5 (Parth): `app.services.processing.process_document` (PR #7) calls `ingest(path)` and saves each returned `Requirement` (`source_req_id`, `raw_text`, `location`).

Handled by the pipeline, which `process_document` relies on:
- every failure is a `ValueError` (`DocumentParseError` for corrupt or encrypted files);
- an empty list means no requirements were found;
- `source_req_id` is the printed ID or `None`; the `UNKNOWN-…` fallback lives only in `id`.

**Follow-up (US-60 branch, migration `0011_project_context`):** add `requirements.section_heading`, `needs_review` and `review_reasons`, and the `document_sections` table; have `process_document` save them. Until then, review flags and sections are computed but not stored.

## 11. Known Limitations
- Multi-column PDFs: blocks are read top-to-bottom, so two columns can interleave.
- Tables in PDFs are read as text blocks; DOCX tables are read row by row (`cell | cell | cell`), including non-ID columns such as priority.
- Heading detection in PDFs is text-based (numbering, case), not font-based.
- No OCR: scanned PDFs fail with a clear message.
- Purely numeric numbering (`3.2.1 The system shall…`) is treated as list or heading numbering, not as a printed ID.
- `.txt` and ReqIF (listed in US-01) are not supported yet.
- FR-06 (user corrects segmentation errors) is not implemented. The `needs_review` flags are what that UI should show first, once they are stored (see §10).

## 12. Plan: Filtering Headings and Prose out of Extraction (Sprint 0 → Sprint 2)

Sprint 0 deliverable; the work is the Sprint 2 task "remove headings and prose from extraction". Goal: a requirements list with no headings, TOC entries, page furniture or narrative, while never silently losing a requirement (US-02, FR-03).

**Already in place (Sprint 1).**

| Content | How it is recognised | Result |
|---|---|---|
| TOC | `Contents` title, dot leaders, DOCX `TOC n` styles, trailing page numbers after a TOC title | excluded (`toc`) |
| Headers, footers, page numbers | PDF margin blocks repeated on half the pages, or bare page numbers | dropped by the PDF parser |
| Headings | DOCX heading styles; numbered or short Title/UPPER case lines without a modal verb or end punctuation | become `section_heading` and open a section |
| Fragments | under 4 words, no punctuation, no modal (table headers, labels) | excluded (`fragment`) |
| Prose under intro-type headings | no modal and heading matches Introduction, Purpose, Scope, Glossary, References, … | excluded (`non_requirement_section`) |
| Other modal-less prose | anywhere else | **kept and flagged** for review |

**Sprint 2 steps, in order (each measured on the planted-conflict benchmark and the realistic fixtures before the next).**

1. **Store the decisions.** Persist `needs_review`, `review_reasons` and `section_heading` (migration `0011`), so the requirements list can show flagged items first and the FR-06 correction UI has something to work with. Store `excluded` as `document_sections` text, never as requirements.
2. **Font-based PDF headings.** Read span size and weight from PyMuPDF and treat a block whose font is larger or bolder than the page's body text as a heading. Removes the main source of headings kept as requirements in PDFs (today detection is text-only).
3. **Section-aware prose rule.** Inside a requirements section (heading matches `requirement|feature|function|interface|constraint|quality` or chapter 3 of an IEEE 830 / ISO 29148 outline), modal-less prose stays flagged; outside one, modal-less prose of two or more sentences is excluded as `narrative`. Single lines with a modal verb are always kept.
4. **Descriptive "will".** "The system will be used by…" in an overview section is description, not a requirement. Exclude `will` sentences in overview-type sections (`product perspective`, `user classes`, `operating environment`, `assumptions`); everywhere else keep them flagged as today.
5. **Numbered headings above list items.** Distinguish `3.2 Login` (heading) from `3.2 The user shall log in` (a numbered requirement) using the modal test already in `_is_heading`, extended to the block-start case that is currently left alone.

**Guardrails.** Anything with a printed ID or `shall`/`must` is never excluded by these rules. Every exclusion keeps a reason and stays in its section, so the context pack still sees it. Accept a step only if requirement recall on the benchmark does not drop; report precision (fewer non-requirements) per step.
