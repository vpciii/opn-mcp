FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY server.py .

RUN pip install --no-cache-dir .

CMD ["python", "server.py"]
