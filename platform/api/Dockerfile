# Platform API and apply worker share this image. Terraform is inside
# because the worker is the one place `terraform apply` runs.
FROM python:3.12-slim

ARG TERRAFORM_VERSION=1.16.6
ARG TARGETARCH=amd64

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip \
    && curl -fsSL -o /tmp/tf.zip "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_${TARGETARCH}.zip" \
    && unzip -q /tmp/tf.zip -d /usr/local/bin && rm /tmp/tf.zip \
    && apt-get purge -y unzip && apt-get autoremove -y && rm -rf /var/lib/apt/lists/* \
    && terraform version

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    WORKER_WORKDIR=/work

RUN useradd --uid 10001 --create-home app && mkdir -p /work && chown app:app /work
WORKDIR /app

# The catalog ships inside the image so the API needs no repo checkout.
COPY platform/api/pyproject.toml /app/
COPY platform/api/platform_api /app/platform_api
COPY platform/catalog /app/catalog
RUN pip install .

USER 10001
ENV CATALOG_DIR=/app/catalog REPO_ROOT=/app
EXPOSE 8000
CMD ["uvicorn", "platform_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
