# syntax=docker/dockerfile:1
#
# Multi-stage build. The "builder" stage has compilers available in case a dependency needs
# to build from source on a given platform (most of ours ship prebuilt wheels, but this keeps
# the build resilient rather than failing on whichever machine turns out to be the exception);
# only the resulting virtualenv is copied into the slim runtime stage — not the toolchain.
#
# This single image serves both the API and the Celery worker (docker-compose.yml picks the
# command); there is deliberately only one image to build, tag and scan.

FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /build
COPY requirements.txt .

# sentence-transformers (Role 2) pulls PyTorch as a transitive dependency, which defaults to
# the CUDA build (~2 GB of nvidia-* packages) on Linux even though this service has no GPU.
# Installing the CPU-only build from PyTorch's own index first satisfies that dependency;
# `pip install -r requirements.txt` then sees it already fulfilled and leaves it alone.
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.2,<3" \
    && pip install -r requirements.txt


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

# libpq5: the runtime half of libpq-dev — psycopg2 needs it even with the prebuilt wheel.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --shell /bin/bash --create-home app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app . .

RUN mkdir -p /data/uploads && chown app:app /data/uploads
VOLUME ["/data/uploads"]

USER app

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
