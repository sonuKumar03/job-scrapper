FROM python:3.13-slim@sha256:bf44cdfcb76cd3b41e879bc058fc37ec5872002ccfde7fcb765e218cde0cd79c AS base
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.12.22@sha256:f513a91fc62fe7c17567eee97230dd198e43edb8a9fbecca843714a4358fe1bc /uv /bin/uv
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app \
    && mkdir /app/data && chown app:app /app/data
COPY pyproject.toml uv.lock readme.md LICENSE alembic.ini ./
COPY migrations ./migrations
COPY src ./src
EXPOSE 8000
CMD ["job-scrapper", "api", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS development
RUN uv sync --frozen --extra web --extra broker --extra export
USER app

FROM base AS production
RUN uv sync --frozen --no-dev --no-editable --extra web --extra broker --extra export
USER app
