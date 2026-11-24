# syntax=docker/dockerfile:1
#
# Three stages. `dev` is last, so a plain build (docker-compose.yml, the E2E workflow) still gets
# the Vite dev server with hot-reload via the bind mount. `prod` is the built SPA served by Caddy,
# which also proxies the API; docker-compose.prod.yml selects it with `target: prod`.

FROM node:20-slim AS build

WORKDIR /app

COPY package.json ./

# Same Windows lockfile problem as the dev stage below (npm/cli#4828).
RUN rm -f package-lock.json && npm install

COPY . .

# Vite bakes this into the bundle; the HTTP client and the /ws socket both derive from it, so it
# must be the full public origin (an empty value would break the WebSocket URL).
ARG VITE_API_BASE_URL
RUN test -n "$VITE_API_BASE_URL" || { echo "VITE_API_BASE_URL is required" >&2; exit 1; }
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build


FROM caddy:2.8-alpine AS prod

COPY --from=build /app/dist /srv
# The Caddyfile is mounted by docker-compose.prod.yml.


FROM node:20-slim AS dev

WORKDIR /app

COPY package.json ./

# The committed package-lock.json was generated on Windows; even `npm install` tries to
# satisfy it with minimal changes rather than re-resolving, which poisons the install on
# Linux (npm/cli#4828 — same issue frontend-ci.yml works around). Force a fresh resolution.
RUN rm -f package-lock.json && npm install

COPY . .

# node:20-slim already ships a "node" user at UID 1000 — reuse it instead of creating one.
RUN chown -R node:node /app
USER node

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD node -e "fetch('http://localhost:5173').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host"]
