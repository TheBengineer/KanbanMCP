FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies
RUN pip install --no-cache-dir \
    fastapi>=0.110.0 \
    uvicorn[standard]>=0.27.0 \
    pydantic>=2.0.0 \
    jinja2 \
    python-multipart

# Copy project
COPY kanban/ /app/kanban/
COPY static/ /app/static/
COPY templates/ /app/templates/
COPY kanban.py /app/

# Create database directory
RUN mkdir -p /app/kanban

EXPOSE 8080

CMD ["python", "kanban.py"]
