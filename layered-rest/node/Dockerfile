FROM python:3.11-slim
RUN apt-get update && apt-get install -y curl
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application code
COPY . .

# Generate gRPC code from proto
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. proto/twopc.proto

RUN chmod +x /app/entrypoint.sh
EXPOSE 8000 50051
ENTRYPOINT ["/app/entrypoint.sh"]
