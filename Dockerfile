FROM python:3.13-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy project specification and install Python dependencies
COPY pyproject.toml uv.lock ./
RUN uv pip install --system -r pyproject.toml --extra web --extra broker

# Copy source code, migrations, and readme
COPY readme.md alembic.ini ./
COPY migrations ./migrations
COPY src ./src

# Install package in editable/system mode
RUN uv pip install --system -e . --no-deps

EXPOSE 8000

CMD ["job-scrapper", "web", "--host", "0.0.0.0", "--port", "8000"]
