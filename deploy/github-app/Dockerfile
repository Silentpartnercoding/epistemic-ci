FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EPISTEMIC_CI_DELIVERY_DB=/data/epistemic-ci-deliveries.sqlite3

WORKDIR /app

RUN addgroup --system epistemic && adduser --system --ingroup epistemic epistemic \
    && mkdir /data && chown epistemic:epistemic /data

COPY deploy/github-app/requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock

COPY . /app

USER epistemic
EXPOSE 8080

CMD ["uvicorn", "epistemic_ci.github_app:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips=*"]
