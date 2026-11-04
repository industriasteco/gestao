FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock .
RUN --mount=type=secret,id=proxy_ca,target=/run/secrets/proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir -r requirements.lock; else pip install --no-cache-dir -r requirements.lock; fi
COPY . .
EXPOSE 8000
CMD ["python","manage.py","runserver","0.0.0.0:8000"]
