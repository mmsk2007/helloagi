FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -e .
EXPOSE 8787
CMD ["helloagi", "serve", "--host", "0.0.0.0", "--port", "8787"]
