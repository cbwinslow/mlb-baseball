## Why

The normal Retrosheet CSV connector is already Python-only, but the raw-event and
box-score paths still require the Chadwick C command-line tools to be installed
outside this project. That means a user can install mlb-baseball with pip or uv
and still fail later when retrosheet_event or retrosheet_box needs cwevent,
cwgame, or cwbox.

The owner wants the Retrosheet path to become a reusable research component that
can eventually be installed and used from Python alone: discover official
Retrosheet files, download/cache them, parse the original event records, and
produce structured results without a system Chadwick installation.

The ecosystem review dated 2026-09-23 found useful prior art but no maintained
package that closes this gap:

- Chadwick is active and remains the correctness reference, but it is a C
  project installed as native binaries.
- pychadwick is a ctypes/scikit-build wrapper around vendored Chadwick C code,
  not a pure-Python implementation.
- pyretrosheet is a useful typed Python parser, but its own documentation says
  it is incomplete and its parser contains source-specific exceptions rather
  than a complete Chadwick-compatible state engine.
- calestini/retrosheet is older Python parser prior art but is also incomplete.
- fungo has a good, current pure-Python Retrosheet download/cache surface for
  official static products, but it does not replace Chadwick's raw event state
  machine.

Retrosheet now publishes official parsed play-by-play CSVs and a Chadwick
crosswalk. That gives this project two independent reference surfaces for a
Python implementation: Chadwick output and Retrosheet's own parsed output.

## What Changes

This change defines and builds the foundation of a standalone Retrosheet Python
package inside the existing uv workspace. It is intentionally separate from
mlb_baseball so that researchers can use it without PostgreSQL, the warehouse,
or model dependencies.

The package will:

- provide a narrow client/catalog for official Retrosheet static files;
- download and cache source artifacts with explicit URL, hash, retrieval time,
  and local-path metadata;
- parse raw Retrosheet record lines into typed, lossless Python objects;
- parse play descriptions into an explicit event representation rather than
  mixing regex parsing with game-state mutation;
- expose streaming iterators so a season does not need to be loaded wholly into
  memory;
- keep pandas/Arrow/Polars conversion outside the parser core;
- define an explicit Chadwick compatibility profile instead of claiming one
  timeless Chadwick behavior;
- ship a differential-test harness that can compare the Python implementation
  with Chadwick 0.10.0 and with Retrosheet's official parsed CSVs.

This first change does NOT switch the production raw-event or box-score
connectors away from Chadwick. It establishes the package boundary, source
client, lossless record/play parsing model, and validation harness. Replacing
cwevent/cwgame and later cwbox is sequenced as follow-up work after measured
parity.

The existing official parsed-CSV connector remains unchanged and remains the
simple Python-only bootstrap path.

## Capabilities

### New Capabilities

- retrosheet-parsing: a standalone Python-only Retrosheet acquisition and
  parsing surface, with lossless source models and explicit compatibility
  validation.

### Modified Capabilities

None in this slice. Existing mlb-baseball connectors keep their current runtime
behavior until a later compatibility gate is satisfied.

## Impact

Expected implementation area:

- packages/<final-retrosheet-distribution-name>/ for the standalone package;
- deterministic package tests and captured small Retrosheet fixtures;
- a reference-only differential test harness that can invoke Chadwick when it is
  available in the test environment;
- OpenSpec documentation for the compatibility contract.

Not changed in this slice:

- mlb_baseball/connectors/retrosheet.py;
- mlb_baseball/connectors/retrosheet_event.py;
- mlb_baseball/connectors/retrosheet_box.py;
- mlb_baseball/chadwick_tools.py production behavior;
- PostgreSQL schemas or migrations;
- current raw/core/gold data contracts.

No native extension is permitted in the package core. A normal package install
must not require a C compiler, CMake, autotools, or a separately installed
Chadwick binary.
