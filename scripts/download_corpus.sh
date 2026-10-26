#!/usr/bin/env bash
# Rebuilds data/raw from the FastAPI docs (MIT licensed, https://github.com/fastapi/fastapi).
# Pinned to one commit so the corpus, and therefore the eval, is reproducible.
set -euo pipefail
COMMIT=7a0a3f0
cd "$(dirname "$0")/.."
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
git clone -q https://github.com/fastapi/fastapi.git "$TMP/src"
git -C "$TMP/src" checkout -q "$COMMIT"
while read -r f; do
  mkdir -p "data/raw/$(dirname "$f")"
  cp "$TMP/src/docs/en/docs/$f" "data/raw/$f"
done <<'FILES'
tutorial/first-steps.md
tutorial/path-params.md
tutorial/query-params.md
tutorial/query-params-str-validations.md
tutorial/body.md
tutorial/body-multiple-params.md
tutorial/body-nested-models.md
tutorial/response-model.md
tutorial/request-files.md
tutorial/handling-errors.md
tutorial/bigger-applications.md
tutorial/sql-databases.md
tutorial/background-tasks.md
tutorial/testing.md
advanced/settings.md
advanced/events.md
advanced/custom-response.md
advanced/advanced-dependencies.md
advanced/behind-a-proxy.md
advanced/websockets.md
deployment/concepts.md
deployment/docker.md
deployment/https.md
deployment/server-workers.md
async.md
advanced/generate-clients.md
advanced/openapi-callbacks.md
advanced/additional-responses.md
python-types.md
tutorial/schema-extra-example.md
FILES
cp "$TMP/src/LICENSE" data/raw/LICENSE-FastAPI.txt
echo "corpus ready in data/raw"
