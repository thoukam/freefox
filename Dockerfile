FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY freefox ./freefox
COPY scripts ./scripts
COPY images ./images

RUN chmod -R a+rX /app && pip install .

CMD ["freefox", "--config", "/etc/freefox/config.yaml"]
