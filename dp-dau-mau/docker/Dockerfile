FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Set PYTHONPATH so uvicorn can find src modules
ENV PYTHONPATH=/app/src
ENV DATA_DIR=/app/data
ENV EXPERIMENT_ID=docker
ENV EPSILON_DAU=0.3
ENV EPSILON_MAU=0.5
ENV DELTA=1e-6
ENV SKETCH_IMPL=kmv

EXPOSE 8000

CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8000"]
