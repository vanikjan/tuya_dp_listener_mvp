ARG BUILD_FROM=python:3.12-alpine
FROM ${BUILD_FROM}

WORKDIR /app
RUN apk add --no-cache ca-certificates
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ /app/
CMD ["python", "-u", "main.py"]
