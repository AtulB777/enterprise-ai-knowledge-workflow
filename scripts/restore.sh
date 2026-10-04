#!/bin/sh
# Restores a backup created by ./scripts/backup.sh into the Docker Compose
# postgres service. Destructive - drops and recreates the target database
# first, so this asks for confirmation before doing anything (ADR-020).
#
# Usage: ./scripts/restore.sh path/to/backup.sql.gz

set -e

BACKUP_FILE="$1"
if [ -z "$BACKUP_FILE" ] || [ ! -f "$BACKUP_FILE" ]; then
    echo "Usage: $0 path/to/backup.sql.gz" >&2
    exit 1
fi

if [ ! -f .env ]; then
    echo "No .env file found in the current directory. Run this from the repo root." >&2
    exit 1
fi
# shellcheck disable=SC1091
. ./.env

DB="${POSTGRES_DB:-enterprise_ai_platform}"
USER="${POSTGRES_USER:-postgres}"

echo "This will DROP and recreate the '$DB' database, replacing all current"
echo "data with the contents of $BACKUP_FILE."
printf "Type the database name (%s) to confirm: " "$DB"
read -r CONFIRMATION
if [ "$CONFIRMATION" != "$DB" ]; then
    echo "Confirmation did not match. Aborting - nothing was changed." >&2
    exit 1
fi

echo "Dropping and recreating $DB ..."
docker compose exec -T postgres psql -U "$USER" -d postgres \
    -c "DROP DATABASE IF EXISTS $DB;" \
    -c "CREATE DATABASE $DB;"

echo "Restoring from $BACKUP_FILE ..."
gunzip -c "$BACKUP_FILE" | docker compose exec -T postgres psql -U "$USER" -d "$DB"

echo "Done. Restart the api/worker services so they pick up the restored data cleanly:"
echo "  docker compose restart api worker"
