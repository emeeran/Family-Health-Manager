# Build frontend static files
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
ARG API_URL=http://localhost:8000
ENV VITE_API_URL=${API_URL}
RUN npm run build

# Caddy serves static files + proxies API to backend
FROM caddy:2-alpine
COPY --from=frontend-builder /app/frontend/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile
USER caddy
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=5s \
  CMD wget -qO- http://localhost:8080/health || exit 1
