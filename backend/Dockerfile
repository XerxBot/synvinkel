FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies into system Python
COPY pyproject.toml ./
RUN uv pip install --system \
    "fastapi[standard]>=0.111.0" \
    "sqlalchemy[asyncio]>=2.0.0" \
    "asyncpg>=0.29.0" \
    "psycopg2-binary>=2.9.9" \
    "pgvector>=0.3.0" \
    "pydantic-settings>=2.3.0" \
    "redis[hiredis]>=5.0.0" \
    "httpx>=0.27.0" \
    "beautifulsoup4>=4.12.0" \
    "lxml>=5.2.0" \
    "trafilatura>=1.9.0" \
    "passlib[bcrypt]>=1.7.4" \
    "python-jose[cryptography]>=3.3.0" \
    "python-multipart>=0.0.9" \
    "feedparser>=6.0.11" \
    "tenacity>=8.3.0" \
    "structlog>=24.2.0"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
