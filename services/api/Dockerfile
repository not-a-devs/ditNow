FROM python:3.13-slim-bookworm AS build
ARG RELEASE_SHA
RUN test "${#RELEASE_SHA}" = 40 && case "$RELEASE_SHA" in *[!0-9a-f]*) exit 2;; esac
ENV UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv==0.13.6
WORKDIR /opt/ditnow
COPY chatbot/ ./chatbot/
COPY services/api/pyproject.toml services/api/uv.lock ./services/api/
WORKDIR /opt/ditnow/services/api
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim-bookworm
ARG RELEASE_SHA
LABEL org.opencontainers.image.revision=$RELEASE_SHA
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH=/opt/ditnow/services/api/.venv/bin:$PATH
RUN groupadd --gid 10001 ditnow && useradd --uid 10001 --gid 10001 --no-create-home ditnow
WORKDIR /opt/ditnow/services/api
COPY --from=build /opt/ditnow/services/api/.venv/ ./.venv/
COPY services/api/app/ ./app/
USER 10001:10001
CMD ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "18000", "--workers", "1", "--loop", "asyncio", "--no-access-log", "--no-proxy-headers"]

