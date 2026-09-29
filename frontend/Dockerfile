# syntax=docker/dockerfile:1
#
# Dev-server image only (Vite's dev server, hot-reload via the docker-compose bind mount).
# Sprint 5 (Dhavni didi) adds a production build stage — `npm run build` output served by
# nginx or shipped to Vercel — once there is real UI to ship.

FROM node:20-slim

WORKDIR /app

COPY package.json ./

# The committed package-lock.json was generated on Windows; even `npm install` tries to
# satisfy it with minimal changes rather than re-resolving, which poisons the install on
# Linux (npm/cli#4828 — same issue frontend-ci.yml works around). Force a fresh resolution.
RUN rm -f package-lock.json && npm install

COPY . .

RUN useradd --uid 1000 --create-home node_app \
    && chown -R node_app:node_app /app
USER node_app

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD node -e "fetch('http://localhost:5173').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host"]
