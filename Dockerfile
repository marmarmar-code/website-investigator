FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir '.[all]' \
    && python -m playwright install --with-deps chromium \
    && useradd --create-home --uid 10001 wi \
    && chown -R wi:wi /app /ms-playwright

USER wi
ENTRYPOINT ["wi"]
CMD ["--help"]
