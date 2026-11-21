"""Updated-SRS tasks (Bansil — US-61, NFR-38).

They run on the ``suggestions`` queue (task names ``suggestions.srs_*``), next to AI suggestions,
so writing an SRS never delays findings or the map. Without a configured model the sections get
their template text — the draft is never left waiting.
"""

import logging
import uuid

from app.classification.llm_client import get_llm_client
from app.core.celery_app import celery_app
from app.core.database import session_scope
from app.srs import generator, service

logger = logging.getLogger(__name__)


@celery_app.task(name=generator.GENERATE)
def generate_task(srs_id: str) -> str | None:
    with session_scope() as db:
        document = generator.generate(db, uuid.UUID(srs_id), get_llm_client())
        return document.status if document else None


@celery_app.task(name=generator.REGENERATE)
def regenerate_task(srs_id: str, key: str) -> str | None:
    with session_scope() as db:
        section = service.regenerate(db, uuid.UUID(srs_id), key, get_llm_client())
        return section.status if section else None
