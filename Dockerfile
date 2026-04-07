FROM python:3.12-slim

RUN groupadd -r bnt && useradd -r -g bnt bnt

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN pip install --no-cache-dir ".[all]" && rm -rf /root/.cache

USER bnt

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["bnt"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
