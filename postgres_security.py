"""Keep Money Tracker's dedicated Postgres schema private to its backend."""


def secure_postgres_schema(cursor, schema="public"):
    """Apply inside the same transaction as table creation; caller commits.

    The app connects as the table owner, which bypasses ordinary RLS. Client
    roles need no policies or grants because this app does not use the Data API.
    Default privileges apply to objects subsequently created by the current role.
    """
    from psycopg2 import sql

    cursor.execute(
        "SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')"
    )
    clients = [sql.SQL("PUBLIC")]
    clients.extend(sql.Identifier(row[0]) for row in cursor.fetchall())
    grantees = sql.SQL(", ").join(clients)
    schema_id = sql.Identifier(schema)

    for object_type in ("TABLES", "SEQUENCES"):
        cursor.execute(sql.SQL(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA {} "
            "REVOKE ALL ON {} FROM {}"
        ).format(schema_id, sql.SQL(object_type), grantees))

    cursor.execute("""
        SELECT c.relname, c.relkind
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND c.relkind IN ('r', 'p', 'S')
        ORDER BY c.relname
    """, (schema,))
    for name, kind in cursor.fetchall():
        relation = sql.Identifier(schema, name)
        if kind != "S":
            cursor.execute(sql.SQL(
                "ALTER TABLE {} ENABLE ROW LEVEL SECURITY"
            ).format(relation))
        cursor.execute(sql.SQL("REVOKE ALL ON {} {} FROM {}").format(
            sql.SQL("SEQUENCE" if kind == "S" else "TABLE"),
            relation, grantees,
        ))
