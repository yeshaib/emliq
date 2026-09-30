FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    EMLIQ_HOME=/data

WORKDIR /app
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY emliq ./emliq
RUN pip install . && useradd --create-home --uid 1000 emliq && mkdir -p /data && chown emliq /data

USER emliq
VOLUME /data
# 8787: web UI. 8765: one-time Google sign-in redirect (only used by `emliq login`).
EXPOSE 8787 8765

HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/api/status')" || exit 1

ENTRYPOINT ["emliq"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8787", "--no-browser"]
