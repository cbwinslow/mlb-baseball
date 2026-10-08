#!/usr/bin/env bash
# Installs the optional PostgreSQL 16 extensions and tools that have no apt
# package (ADR-302): downloaded from their upstream GitHub releases or built from
# source. Run it yourself so you see exactly what is fetched; it is idempotent.
#
#   scripts/pg_extensions_github.sh            # everything below
#   scripts/pg_extensions_github.sh pg_graphql # just one step
#
# Targets the PG16 server tools (/usr/lib/postgresql/16). It does NOT restart
# Postgres and does NOT create extensions in any database -- apply
# migrations/0116_postgres_extensions.sql afterwards.
set -euo pipefail

# Put PG16 first: some builds (multicorn2's Python helper) call a bare `pg_config`,
# which otherwise resolves to the PG18 client on this machine.
export PATH=/usr/lib/postgresql/16/bin:$PATH
PG_CONFIG=/usr/lib/postgresql/16/bin/pg_config
WORK="$(mktemp -d)"
trap 'sudo rm -rf "$WORK"' EXIT
BIN="$HOME/.local/bin"
mkdir -p "$BIN"

gh_asset() { # repo tag asset -> downloads into $WORK
  curl -fsSL -o "$WORK/$3" "https://github.com/$1/releases/download/$2/$3"
}

pgvectorscale() {
  gh_asset timescale/pgvectorscale 0.9.1 pgvectorscale-0.9.1-pg16-amd64.zip
  (cd "$WORK" && unzip -oq pgvectorscale-0.9.1-pg16-amd64.zip && sudo dpkg -i ./*pgvectorscale*.deb)
}

pg_graphql() {
  gh_asset supabase/pg_graphql v1.6.2 pg_graphql-v1.6.2-pg16-amd64-linux-gnu.deb
  sudo dpkg -i "$WORK/pg_graphql-v1.6.2-pg16-amd64-linux-gnu.deb"
}

pg_column_tetris() { # pure SQL extension
  git clone --depth 1 https://github.com/rogerwelin/pg_column_tetris.git "$WORK/tetris"
  sudo make -C "$WORK/tetris" install PG_CONFIG="$PG_CONFIG"
}

multicorn2() { # Python foreign data wrapper
  sudo apt-get install -y python3-dev python3-setuptools
  git clone --depth 1 https://github.com/pgsql-io/multicorn2.git "$WORK/multicorn2"
  make -C "$WORK/multicorn2" PG_CONFIG="$PG_CONFIG"
  sudo env "PATH=$PATH" make -C "$WORK/multicorn2" install PG_CONFIG="$PG_CONFIG"
}

tbls() {
  gh_asset k1LoW/tbls v1.96.1 tbls_1.96.1-1_amd64.deb
  sudo dpkg -i "$WORK/tbls_1.96.1-1_amd64.deb"
}

pgedge_mcp() {
  gh_asset pgEdge/pgedge-postgres-mcp v1.1.0 pgedge-postgres-mcp-server_1.1.0_linux_x86_64.tar.gz
  tar -xzf "$WORK/pgedge-postgres-mcp-server_1.1.0_linux_x86_64.tar.gz" -C "$BIN"
}

postgres_dba() { # interactive psql menu; start with: psql -d mlb -f ~/.local/share/postgres_dba/start.psql
  rm -rf "$HOME/.local/share/postgres_dba"
  git clone --depth 1 https://github.com/NikolayS/postgres_dba.git "$HOME/.local/share/postgres_dba"
}

atlas() {
  curl -fsSL -o "$BIN/atlas" https://release.ariga.io/atlas/atlas-linux-amd64-latest
  chmod +x "$BIN/atlas"
}

node_tools() { # postgres.ai CLI and Azimutt schema explorer CLI
  npm install -g postgresai azimutt
}

pgai() { # Python library + `pgai install -d <url>` creates its schema in a database
  uv tool install --force pgai
}

steps=(pgvectorscale pg_graphql pg_column_tetris multicorn2 tbls pgedge_mcp postgres_dba atlas node_tools pgai)
[[ $# -gt 0 ]] && steps=("$@")
for s in "${steps[@]}"; do echo "== $s"; "$s"; done
