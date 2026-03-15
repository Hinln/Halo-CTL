FROM python:3.11-slim AS runtime

RUN useradd -m -u 10001 app
WORKDIR /app

COPY pyproject.toml README.md requirements.txt halo_publish.py /app/
COPY halo_cli /app/halo_cli

RUN pip install --no-cache-dir -U pip \
  && pip install --no-cache-dir .

USER app

ENTRYPOINT ["python", "halo_publish.py"]

