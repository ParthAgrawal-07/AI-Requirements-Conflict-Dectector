# Document Ingestion & Extraction Module Design (Sprint 0)

## 1. Purpose of the Ingestion Module
The ingestion module is responsible for reading source Software Requirements Specifications (SRS) documents and parsing them into a structured format. It performs the initial extraction of text and basic segmentation to isolate individual requirements before they are sent to the embedding and classification stages.

## 2. PDF Parsing Decision (PyMuPDF)
We selected `PyMuPDF` (`fitz`) because our expected SRS documents are born-digital, structured PDFs. PyMuPDF is extremely fast, lightweight, and handles text extraction across pages reliably without the heavy overhead or dependencies of OCR libraries (which we explicitly avoided in Sprint 0).

## 3. DOCX Parsing Decision (python-docx)
We selected `python-docx` as the standard for parsing Microsoft Word documents. It is a mature, robust library specifically designed for reading the `.docx` XML structure, allowing us to accurately iterate through paragraphs without parsing binary formats.

## 4. Supported Formats
- `.pdf` (born-digital)
- `.docx` (Office Open XML)

## 5. Unsupported Formats
- `.doc` (older binary format)
- `.txt`, `.odt`, and other undocumented formats
Any attempt to ingest these will raise a clear `ValueError` exception.

## 6. RawSegment Schema
The intermediate model representing extracted chunks (before requirement segmentation):
- `text` (str)
- `source_document` (str)
- `page_or_paragraph` (int)
- `section_heading` (str | None)
- `order_index` (int)

*Note: For PDFs, `page_or_paragraph` maps to the page number. For DOCX, it maps to the paragraph index. The schema remains format-agnostic.*

## 7. Requirement Schema
The final output model representing a segmented requirement:
- `id` (str)
- `raw_text` (str)
- `source_document` (str)
- `location` (str)
- `extracted_at` (datetime)

## 8. Parser Abstraction
We define a generic `Parser` abstract base class with a `parse(file_path: str) -> List[RawSegment]` method. Both `PDFParser` and `DOCXParser` implement this, ensuring a uniform interface for the rest of the pipeline.

## 9. Basic Segmentation Approach
In Sprint 0, segmentation is a simple, deterministic proof-of-concept. It iterates through the text of each segment line-by-line and uses regex patterns to look for common identifiers like `REQ-001` or `FR-1.2`. If no ID is found, it falls back to a deterministic unknown ID format: `UNKNOWN-<page/para_num>-<index>`.

## 10. Known Sprint 0 Limitations
- Segmentation is extremely basic (regex line matching) and NOT production-ready.
- Layout reconstruction for PDFs (e.g., detecting multi-column layouts, tables) is not implemented.
- Section headings in DOCX/PDFs are not reliably mapped to segments yet.

## 11. What will be improved in Sprint 1
- Production-quality rule-based segmentation (handling multi-paragraph requirements).
- Better parsing of structured lists and headings as context.
- Advanced layout heuristics for PDF extraction.
