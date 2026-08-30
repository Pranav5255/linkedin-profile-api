FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml LICENSE README.md ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip && pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.12-slim

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin app \
    && mkdir -p /data \
    && chown app:app /data

WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
COPY --chown=app:app src ./src
COPY --chown=app:app samples ./samples
COPY --chown=app:app pyproject.toml LICENSE ./

USER app
EXPOSE 8000
VOLUME ["/data"]
ENV CACHE_DATABASE_PATH=/data/cache.db
ENV CAPTURED_ENDPOINTS_PATH=/data/captured-endpoints.json
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"

CMD ["linkedin-profile-api", "serve", "--host", "0.0.0.0", "--port", "8000"]
