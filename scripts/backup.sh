#!/bin/sh
# Backs up the Docker Compose postgres service's data via pg_dump, run
# *inside* the postgres container (so it always matches whatever server
# version is actually running, rather than requiring a matching pg_dump
# client installed on the host) - ADR-020.
#
# Usage: ./scripts/backup.sh [output-directory]
# Defaults to ./backups/ if no directory given.

set -e

OUTPUT_DIR="${1:-./backups}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_FILE="$OUTPUT_DIR/enterprise_ai_platform-$TIMESTAMP.sql.gz"

if [ ! -f .env ]; then
    echo "No .env file found in the current directory. Run this from the repo root," >&2
    echo "after 'cp .env.example .env', so POSTGRES_USER/DB match the running stack." >&2
    exit 1
fi
# shellcheck disable=SC1091
. ./.env

mkdir -p "$OUTPUT_DIR"

echo "Backing up ${POSTGRES_DB:-enterprise_ai_platform} to $OUTPUT_FILE ..."
docker compose exec -T postgres \
    pg_dump -U "${POSTGRES_USER:-postgres}" "${POSTGRES_DB:-enterprise_ai_platform}" \
    | gzip > "$OUTPUT_FILE"

echo "Done: $OUTPUT_FILE ($(du -h "$OUTPUT_FILE" | cut -f1))"
