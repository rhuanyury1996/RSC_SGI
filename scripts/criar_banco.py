"""Cria role e database PostgreSQL para o SGI RSC.

Uso (PowerShell):
  $env:POSTGRES_ADMIN_PASSWORD = "sua_senha_do_usuario_postgres"
  .\\.venv\\Scripts\\python.exe scripts\\criar_banco.py
"""

from __future__ import annotations

import os
import sys

import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

load_dotenv()

DB_NAME = os.getenv("POSTGRES_DB", "sgi_rsc")
DB_USER = os.getenv("POSTGRES_USER", "sgi_rsc")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "sgi_rsc_dev")
HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
PORT = os.getenv("POSTGRES_PORT", "5432")
ADMIN_USER = os.getenv("POSTGRES_ADMIN_USER", "postgres")
ADMIN_PASSWORD = os.getenv("POSTGRES_ADMIN_PASSWORD")


def main() -> int:
    if not ADMIN_PASSWORD:
        print("Defina POSTGRES_ADMIN_PASSWORD com a senha do usuário postgres.")
        return 1

    try:
        conn = psycopg2.connect(
            dbname="postgres",
            user=ADMIN_USER,
            password=ADMIN_PASSWORD,
            host=HOST,
            port=PORT,
            client_encoding="UTF8",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Falha ao conectar no PostgreSQL como {ADMIN_USER}: {exc!r}")
        return 1

    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (DB_USER,))
    if not cur.fetchone():
        cur.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(DB_USER),
                sql.Literal(DB_PASSWORD),
            )
        )
        print(f"Role criada: {DB_USER}")
    else:
        cur.execute(
            sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                sql.Identifier(DB_USER),
                sql.Literal(DB_PASSWORD),
            )
        )
        print(f"Role já existia; senha atualizada: {DB_USER}")

    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
    if not cur.fetchone():
        cur.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(DB_NAME),
                sql.Identifier(DB_USER),
            )
        )
        print(f"Database criada: {DB_NAME}")
    else:
        print(f"Database já existe: {DB_NAME}")

    cur.close()
    conn.close()
    print("Pronto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
