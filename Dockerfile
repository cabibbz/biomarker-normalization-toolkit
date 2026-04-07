FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir ".[rest]"

EXPOSE 8000

ENTRYPOINT ["bnt"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
