FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies
RUN pip install --no-cache-dir fastapi uvicorn[standard] pydantic jinja2 python-multipart

# Copy project
COPY kanban/ /app/kanban/
COPY static/ /app/static/
COPY templates/ /app/templates/

ENV PYTHONPATH=/app

ENV PYTHONPATH=/app

EXPOSE 8080

CMD ["python3", "-m", "uvicorn", "kanban.web:app", "--host", "0.0.0.0", "--port", "8080"]
