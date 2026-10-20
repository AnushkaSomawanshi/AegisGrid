FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY runner.py .
EXPOSE 8010
CMD ["uvicorn", "runner:app", "--host", "0.0.0.0", "--port", "8010"]
