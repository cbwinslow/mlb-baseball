#!/usr/bin/env bash
set -euo pipefail

echo "=== Setting up MLB Research Platform dev environment ==="

# Wait for PostgreSQL
until pg_isready -h db -U postgres; do
  echo "Waiting for PostgreSQL service..."
  sleep 1
done

# Ensure test database exists
PGPASSWORD=postgres psql -h db -U postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'mlb_test'" | grep -q 1 || \
  PGPASSWORD=postgres psql -h db -U postgres -c "CREATE DATABASE mlb_test;"

# Install Python project and dependencies
uv pip install --system -e ".[dev]"

# Ensure .env file exists if missing
if [ ! -f .env ]; then
  cp .env.example .env
  sed -i 's|localhost|db|g' .env
fi

echo "=== Setup complete! Run 'mlb doctor' or 'pytest' to verify ==="
