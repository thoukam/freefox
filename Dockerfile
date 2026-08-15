FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends rsync openssh-client \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY freefox ./freefox
COPY scripts ./scripts
COPY images ./images

RUN chmod -R a+rX /app && pip install .

CMD ["freefox", "--config", "/etc/freefox/config.yaml"]
