# V4 Pro — AI Code Quality Gate
# One-command: docker run --rm -v $(pwd):/code ghcr.io/yn400/v4-pro verify --code /code

FROM python:3.11-slim

WORKDIR /app

# Install v4-pro
COPY . .
RUN pip install -e . --no-cache-dir

# Entry point
ENTRYPOINT ["v4-pro"]
CMD ["--help"]
