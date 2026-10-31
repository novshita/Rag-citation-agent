# RAG Citation Agent API.
#
#   docker build -t rag-agent .
#   docker run --rm -p 8000:8000 --env-file .env -v "$PWD/data:/app/data" rag-agent
#
# The index (data/chroma) and the secrets (.env) are NOT in the image: mount them.
# Build the index first, either on the host (python -m rag ingest data/raw) or in the image:
#   docker run --rm --env-file .env -v "$PWD/data:/app/data" rag-agent python -m rag ingest data/raw
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

RUN useradd --create-home app && mkdir -p /app/data && chown -R app /app/data /opt/hf
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "rag.api:create_default_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
