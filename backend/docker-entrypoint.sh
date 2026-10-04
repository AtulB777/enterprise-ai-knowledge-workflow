#!/bin/sh
set -e

# Only the api service's default CMD (uvicorn ...) runs migrations here -
# the worker service overrides CMD to `arq ...` in docker-compose.yml, so
# this conditional naturally skips migrating there too. The worker instead
# depends_on the api service with condition: service_healthy, which only
# passes once uvicorn is actually serving - i.e. after this exact migration
# step has already completed. See ADR-019 decision 2.
if [ "$1" = "uvicorn" ]; then
    echo "Running database migrations..."
    alembic upgrade head
fi

exec "$@"
