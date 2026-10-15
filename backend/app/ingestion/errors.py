"""Exceptions raised by the ingestion pipeline."""


class DocumentParseError(ValueError):
    """
    A supported-format file could not be read (corrupted or encrypted).

    Subclasses ValueError so callers that already catch ValueError for
    unsupported formats also handle this case (FR-02: reject and notify).
    """
