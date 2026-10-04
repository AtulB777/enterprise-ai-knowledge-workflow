# syntax=docker/dockerfile:1

# --- deps: install once, cached separately from source changes.
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# --- builder: real production build.
FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* variables are inlined into the client bundle at build time,
# not read at container runtime (ADR-019 decision 3) - must be a build arg,
# not just a docker-compose `environment:` entry, or this would silently do
# nothing. Defaults to the URL the *browser* needs (the host machine,
# outside the Docker network), not the internal `api` service hostname.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

RUN npm run build

# --- runner: minimal image, only the traced standalone output.
FROM node:22-slim AS runner
WORKDIR /app

RUN useradd --create-home --shell /bin/bash app
ENV NODE_ENV=production

COPY --from=builder --chown=app:app /app/.next/standalone ./
COPY --from=builder --chown=app:app /app/.next/static ./.next/static
COPY --from=builder --chown=app:app /app/public ./public

USER app
EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
    CMD node -e "fetch('http://localhost:3000/login').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
