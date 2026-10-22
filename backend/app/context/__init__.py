"""Project context (Bansil — US-60, FR-103 to FR-105, ADR-28).

* :mod:`app.context.brief` — the brief schema: fields, labels, required set, field status;
* :mod:`app.context.drafter` — ``BriefDrafter``: drafts the brief from an initial SRS (FR-104);
* :mod:`app.context.service` — ``ProjectContextService``: versions, confirmation, activation
  and the missing-fields message of the ContextGate (FR-103).

The context pack sent with every LLM call (FR-105) is built by Keval's ``ContextPackBuilder``
(``app/classification/context_pack.py``) from ``service.confirmed_values(confirmed_context(...))``,
so AI-drafted fields never reach the LLM unconfirmed.
"""
