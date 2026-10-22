# Sample Documents

Ingestion tests generate their documents on the fly (see `backend/tests/ingestion/conftest.py`), so nothing here is needed to run the tests:

- `realistic_srs_pdf`: a 3-page SRS with a title page, a table of contents, a running header/footer, wrapped lines, a requirement split across a page break, a bullet list, statements without IDs, and a duplicate ID.
- `realistic_srs_docx`: styled headings, a glossary, a Word bullet list, and a requirements table with a header row.

Add real-world SRS documents here (born-digital PDF or DOCX) for manual validation of the pipeline.
