FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY proxy.py .
COPY config.yaml .

VOLUME ["/app/logs"]

EXPOSE 3128
CMD ["python", "proxy.py"]
