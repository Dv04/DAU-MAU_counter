FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DATA_DIR={{DATA_DIR}}
ENV EXPERIMENT_ID={{EXPERIMENT_ID}}
ENV EPSILON_DAU={{EPSILON_DAU}}
ENV EPSILON_MAU={{EPSILON_MAU}}
ENV DELTA={{DELTA}}
ENV SKETCH_IMPL={{SKETCH_IMPL}}

EXPOSE 8000

CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8000"]
