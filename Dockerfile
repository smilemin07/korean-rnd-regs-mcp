FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN pip install --no-cache-dir .

ENV PORT=8080
EXPOSE 8080

CMD ["korean-rnd-regs-mcp", "--http"]
