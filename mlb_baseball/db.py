import psycopg

from mlb_baseball.config import database_url


def get_connection() -> psycopg.Connection:
    return psycopg.connect(database_url())
