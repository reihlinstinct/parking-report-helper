# syntax=docker/dockerfile:1

FROM python:3.13-slim AS build
WORKDIR /src
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels .

# Run the test suite: docker build --target test .
FROM python:3.13-slim AS test
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl
COPY sample.json ./sample.json
COPY tests ./tests
COPY docs ./docs
RUN python -m unittest discover -s tests -v

FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
RUN useradd --create-home --uid 10001 app
USER app
WORKDIR /data
ENTRYPOINT ["parking-report"]
CMD ["--help"]
