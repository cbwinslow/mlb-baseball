// Runs visitor SQL against the published MLB Research Statistic Backbone
// dataset entirely in the browser via DuckDB-WASM. No project-operated
// query backend: after this module and duckdb-wasm's own assets load, every
// request goes to Hugging Face only (delivery-surface change, design.md D4).

import * as duckdb from "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.32.0/+esm";

const HF_REPO_ID = "cbwinslow/mlb-research";
// "main" until the first tagged release is published (task 5.1); task 5.2
// points this at the released tag once one exists.
const HF_REVISION = "main";

// The eight backbone tables eligible for publication -- see
// openspec/changes/delivery-surface/rights-review.md. player_season/
// team_season are excluded on source-rights grounds and are not registered.
const BACKBONE_TABLES = [
  "batting_game",
  "pitching_game",
  "batting_season",
  "pitching_season",
  "batting_team",
  "pitching_team",
  "batting_career",
  "pitching_career",
];

function parquetUrl(table) {
  return `https://huggingface.co/datasets/${HF_REPO_ID}/resolve/${HF_REVISION}/data/${table}.parquet`;
}

const statusEl = document.getElementById("status");
const errorEl = document.getElementById("error");
const resultsEl = document.getElementById("results");
const sqlEl = document.getElementById("sql");
const runButton = document.getElementById("run");

function setStatus(text) {
  statusEl.textContent = text;
}

function showError(message) {
  errorEl.textContent = message;
  errorEl.hidden = false;
}

function clearError() {
  errorEl.hidden = true;
  errorEl.textContent = "";
}

function renderResults(result) {
  resultsEl.innerHTML = "";
  const columns = result.schema.fields.map((f) => f.name);
  const rows = result.toArray().map((row) => row.toJSON());

  const table = document.createElement("table");

  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  for (const col of columns) {
    const th = document.createElement("th");
    th.textContent = col;
    headerRow.appendChild(th);
  }
  thead.appendChild(headerRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const col of columns) {
      const td = document.createElement("td");
      const value = row[col];
      td.textContent = value === null || value === undefined ? "" : String(value);
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  resultsEl.appendChild(table);

  setStatus(`${rows.length} row${rows.length === 1 ? "" : "s"}`);
}

let conn;

async function init() {
  setStatus("Loading DuckDB-WASM...");
  const bundles = duckdb.getJsDelivrBundles();
  const bundle = await duckdb.selectBundle(bundles);
  const workerUrl = URL.createObjectURL(
    new Blob([`importScripts("${bundle.mainWorker}");`], { type: "text/javascript" })
  );
  const worker = new Worker(workerUrl);
  const logger = new duckdb.ConsoleLogger();
  const db = new duckdb.AsyncDuckDB(logger, worker);
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
  URL.revokeObjectURL(workerUrl);

  conn = await db.connect();

  setStatus("Registering backbone tables...");
  for (const table of BACKBONE_TABLES) {
    await conn.query(`CREATE VIEW ${table} AS SELECT * FROM read_parquet('${parquetUrl(table)}')`);
  }

  setStatus("Ready.");
  runButton.disabled = false;
}

async function runQuery() {
  if (!conn) return;
  clearError();
  runButton.disabled = true;
  setStatus("Running...");
  try {
    const result = await conn.query(sqlEl.value);
    renderResults(result);
  } catch (err) {
    resultsEl.innerHTML = "";
    setStatus("Error.");
    showError(err && err.message ? err.message : String(err));
  } finally {
    runButton.disabled = false;
  }
}

runButton.addEventListener("click", runQuery);

init().catch((err) => {
  setStatus("Failed to load DuckDB-WASM.");
  showError(err && err.message ? err.message : String(err));
});
