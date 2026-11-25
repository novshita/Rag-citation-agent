# RAG Citation Agent API.
#
#   docker build -t rag-agent .
#   docker run --rm -p 8000:8000 --env-file .env -v "$PWD/data:/app/data" rag-agent
#
# The sample documents (data/raw) are indexed while the image is built, so the image is self-contained and
# can run on a host that can't mount a folder. The secrets (.env) are NOT in the image: pass them in at run time.
# Optional: -v "$PWD/data:/app/data" keeps accounts and the query log between runs (it also replaces the baked index
# with the one in that folder).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf

WORKDIR /app

# CPU-only PyTorch first: the default Linux wheel bundles GPU libraries and adds gigabytes.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[api]"

# Bake the embedding model into the image so the first request doesn't download it.
ARG EMBEDDING_MODEL=all-MiniLM-L6-v2
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"

# Index the sample documents now (embeddings are computed here, once, not on every start).
COPY data/raw ./data/raw
RUN python -m rag ingest data/raw

RUN useradd --create-home app && mkdir -p /app/data && chown -R app /app/data /opt/hf
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "rag.api:create_default_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
