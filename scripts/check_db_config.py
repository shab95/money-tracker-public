
import sys
import os

# Add parent dir to path (project root)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import psycopg2
    print(f"Psycopg2: {psycopg2.__version__}")
except ImportError:
    print("Psycopg2: Not Found")

try:
    import app_secrets
    print(f"Secrets Found: {app_secrets.__file__}")
    print(f"DIRECT_CONNECTION: {getattr(app_secrets, 'DIRECT_CONNECTION', 'Not Found')}")
except ImportError:
    print("Secrets: Not Found")

import db
print(f"DB_URL in db.py: {db.DB_URL}")
print(f"Is Postgres: {db.is_postgres()}")
