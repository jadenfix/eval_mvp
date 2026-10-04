FROM python:3.13.7-slim-bookworm
RUN mkdir -p /app /logs/verifier && useradd -u 1000 tester
COPY . /tests
RUN chmod -R 700 /tests && chmod 755 /app /logs/verifier
WORKDIR /tests
