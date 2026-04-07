FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/
RUN pip install --no-cache-dir --prefix=/install ".[all]"

FROM python:3.12-slim
RUN groupadd -r bnt && useradd -r -g bnt bnt
COPY --from=builder /install /usr/local
WORKDIR /app
COPY src/ src/
USER bnt
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
ENTRYPOINT ["bnt"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
