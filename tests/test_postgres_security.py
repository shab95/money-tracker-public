"""Opt-in database security checks; every change is rolled back."""

import os
import uuid

import pytest

from postgres_security import secure_postgres_schema


@pytest.mark.skipif(
    not os.getenv("MONEY_TRACKER_SECURITY_TEST_DSN"),
    reason="Requires an explicitly supplied Postgres security test connection",
)
def test_private_schema_blocks_clients_and_preserves_backend_access():
    import psycopg2
    from psycopg2 import sql

    schema = "security_test_" + uuid.uuid4().hex
    conn = psycopg2.connect(
        os.environ["MONEY_TRACKER_SECURITY_TEST_DSN"],
        sslmode="require", connect_timeout=10,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '15s'")
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            cursor.execute(
                "SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')"
            )
            roles = [row[0] for row in cursor.fetchall()]
            assert set(roles) == {"anon", "authenticated"}
            for role in roles:
                cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(schema), sql.Identifier(role),
                ))
            table = sql.Identifier(schema, "items")
            cursor.execute(sql.SQL(
                "CREATE TABLE {} (id SERIAL PRIMARY KEY, payload TEXT)"
            ).format(table))
            # Simulate the insecure defaults used by older Supabase projects.
            cursor.execute(sql.SQL(
                "GRANT ALL ON TABLE {} TO PUBLIC, anon, authenticated"
            ).format(table))
            cursor.execute(sql.SQL(
                "GRANT ALL ON ALL SEQUENCES IN SCHEMA {} TO anon, authenticated"
            ).format(sql.Identifier(schema)))
            cursor.execute(sql.SQL(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA {} "
                "GRANT ALL ON TABLES TO anon, authenticated"
            ).format(sql.Identifier(schema)))
            cursor.execute(sql.SQL(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA {} "
                "GRANT ALL ON SEQUENCES TO anon, authenticated"
            ).format(sql.Identifier(schema)))

            secure_postgres_schema(cursor, schema)
            secure_postgres_schema(cursor, schema)  # Safe to reapply on startup.

            # The backend still supports actual reads, inserts, updates, deletes.
            cursor.execute(sql.SQL(
                "INSERT INTO {} (payload) VALUES ('probe') RETURNING id"
            ).format(table))
            item_id = cursor.fetchone()[0]
            cursor.execute(sql.SQL("SELECT payload FROM {} WHERE id = %s").format(table), (item_id,))
            assert cursor.fetchone()[0] == "probe"
            cursor.execute(sql.SQL("UPDATE {} SET payload = 'updated' WHERE id = %s").format(table), (item_id,))
            assert cursor.rowcount == 1
            cursor.execute(sql.SQL("DELETE FROM {} WHERE id = %s").format(table), (item_id,))
            assert cursor.rowcount == 1

            cursor.execute("SELECT relrowsecurity FROM pg_class WHERE oid = %s::regclass", (f"{schema}.items",))
            assert cursor.fetchone()[0]
            for role in roles:
                for statement in (
                    "SELECT * FROM {} LIMIT 0",
                    "INSERT INTO {} (payload) VALUES ('denied')",
                    "UPDATE {} SET payload = 'denied' WHERE false",
                    "DELETE FROM {} WHERE false",
                ):
                    cursor.execute("SAVEPOINT client_check")
                    cursor.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
                    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                        cursor.execute(sql.SQL(statement).format(table))
                    cursor.execute("ROLLBACK TO SAVEPOINT client_check")
                cursor.execute(
                    "SELECT has_sequence_privilege(%s, %s, 'USAGE, SELECT, UPDATE')",
                    (role, f"{schema}.items_id_seq"),
                )
                assert not cursor.fetchone()[0]

            # Future tables and serial sequences do not inherit client access.
            cursor.execute(sql.SQL("CREATE TABLE {} (id SERIAL)").format(
                sql.Identifier(schema, "future_items"),
            ))
            for role in roles:
                cursor.execute(
                    "SELECT has_table_privilege(%s, %s, 'SELECT, INSERT, UPDATE, DELETE'), "
                    "has_sequence_privilege(%s, %s, 'USAGE, SELECT, UPDATE')",
                    (role, f"{schema}.future_items", role, f"{schema}.future_items_id_seq"),
                )
                assert cursor.fetchone() == (False, False)
            secure_postgres_schema(cursor, schema)
            cursor.execute("SELECT relrowsecurity FROM pg_class WHERE oid = %s::regclass", (f"{schema}.future_items",))
            assert cursor.fetchone()[0]
    finally:
        conn.rollback()
        conn.close()
