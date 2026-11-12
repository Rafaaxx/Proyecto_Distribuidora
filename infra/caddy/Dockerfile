# Imagen de Caddy de PRODUCCION con el frontend compilado adentro (change 27a, D4).
# Contexto: la raiz del repositorio (ver docker-compose.prod.yml).
#   Etapa 1: compila el frontend con la misma APP_VERSION que el backend (change 22b, D7).
#   Etapa 2: Caddy sirve la compilacion en /srv con el Caddyfile de produccion.

FROM node:22-slim AS frontend

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci

COPY frontend/ ./

ARG APP_VERSION
ENV APP_VERSION=$APP_VERSION
RUN npm run build

FROM caddy:2

COPY --from=frontend /app/dist /srv
COPY infra/caddy/Caddyfile /etc/caddy/Caddyfile
COPY infra/caddy/encabezados.caddy /etc/caddy/encabezados.caddy
