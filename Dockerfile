FROM python:3.12-slim
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY data ./data
COPY dbt ./dbt
COPY docs ./docs
COPY eval ./eval
ENV ERP_COPILOT_HOME=/app
# Build the warehouse and SOP index at image build time (synthetic data only), then drop root.
RUN python -m erp_copilot.pipeline all && rm -rf dbt/target dbt/logs logs && chown -R app:app /app
USER 10001
EXPOSE 8000
# LLM_PROVIDER / LLM_BASE_URL point at an Ollama or OpenAI-compatible (e.g. vLLM) server.
CMD ["uvicorn", "erp_copilot.api:app", "--host", "0.0.0.0", "--port", "8000"]
