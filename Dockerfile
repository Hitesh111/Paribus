FROM python:3.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 1. Install dependencies using a dummy package to utilize Docker caching
COPY pyproject.toml README.md ./
RUN mkdir app && touch app/__init__.py \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# 2. Copy the actual application source code and install it (installs instantly as dependencies are cached)
COPY app ./app
RUN pip install --no-cache-dir --no-deps .

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
