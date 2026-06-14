import os
from qdrant_client import QdrantClient
from dotenv import load_dotenv

load_dotenv()

# Explicitly print to check if values are loaded
url = os.getenv("QDRANT_URL")
key = os.getenv("QDRANT_API_KEY")

print(f"URL: {url}")
print(f"Key present: {key is not None}")

client = QdrantClient(
    url=url,
    api_key=key,
    prefer_grpc=True  # Force gRPC, it's often more stable than REST for Qdrant Cloud
)

try:
    print(client.get_collections())
except Exception as e:
    print(f"Error: {e}")