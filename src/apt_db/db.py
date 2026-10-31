"""Database connection used by every program in this project."""
import os

import psycopg

# Local demo database from docker-compose.yml. Override with the TRIALDB_DSN environment variable.
DSN = os.environ.get("TRIALDB_DSN", "postgresql://postgres:trialdb@localhost:5433/trialdb")


def connect():
    return psycopg.connect(DSN)
