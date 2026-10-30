FROM node:22-bookworm-slim AS build
ARG RELEASE_SHA
RUN test "${#RELEASE_SHA}" = 40 && case "$RELEASE_SHA" in *[!0-9a-f]*) exit 2;; esac
WORKDIR /build
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
# Do not bake an origin or a secret into VITE_*; the client defaults to /api/v1.
RUN npm run build

FROM nginx:1.28-alpine
ARG RELEASE_SHA
LABEL org.opencontainers.image.revision=$RELEASE_SHA
COPY infra/deploy/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /build/dist/ /srv/ditnow-web/
USER 101:101
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]

