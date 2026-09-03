"""One-time DB setup: enables pgvector and creates the documents/chunks schema.

Run with: python Backend.py
"""

from app.db import init_schema

if __name__ == "__main__":
    init_schema()
    print("Connected and schema initialized successfully")
