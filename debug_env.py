import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

print(f"Python Executable: {sys.executable}")
try:
    import app_secrets
    print("✅ app_secrets imported")
    if getattr(app_secrets, 'DB_CONNECTION_STRING', None):
        print("✅ DB_CONNECTION_STRING found")
    elif getattr(app_secrets, 'DIRECT_CONNECTION', None):
        print("✅ DIRECT_CONNECTION found")
    else:
        print("❌ No connection string found in app_secrets")
except Exception as e:
    print(f"❌ Failed to import app_secrets: {e}")

try:
    import psycopg2
    print(f"✅ psycopg2 imported (Version: {psycopg2.__version__})")
except ImportError:
    print("❌ psycopg2 NOT installed or import failed")

import db
print(f"DB is_postgres(): {db.is_postgres()}")
