## 1. Toolchain

- [x] 1.1 Add `[project.optional-dependencies] docs = ["mkdocs>=1.6", "mkdocs-material>=9.5"]`
  to `pyproject.toml`; run `uv lock` and `uv sync --extra docs`. Verify: `uv run mkdocs --version`
  prints a version and `uv lock --check` exits 0.
  — Done: `mkdocs 1.6.1`, `mkdocs-material 9.7.7` locked; `uv lock --check` clean.
  `uv sync --all-extras` used to keep dev/export tooling in the same venv.

## 2. Scaffold the site

- [x] 2.1 `git mv docs/site/query docs/site-src/query` (create `docs/site-src/`).
  Verify: `docs/site-src/query/index.html` and `query.js` exist; `docs/site/` no
  longer tracked content under `query/`. — Done: staged as `R100` renames.
- [x] 2.2 Add `/docs/site/` to `.gitignore` with a comment that it is `mkdocs build`
  output. Verify: `git status --porcelain docs/site` is empty after a build.
  — Done: `git check-ignore docs/site/index.html` matches; status clean after build.
- [x] 2.3 Create `mkdocs.yml` at repo root: `site_name`, `docs_dir: docs/site-src`,
  `site_dir: docs/site`, `theme: material` (light/dark toggle), repo_url, the
  `pymdownx.snippets` (`base_path: [docs]`, `check_paths: true`),
  `pymdownx.superfences`, `pymdownx.arithmatex`,
  (for the formula page) markdown extensions, and a `nav` with Home, Data
  dictionary, Grain ladder, Formulas, Limitations, and Query. Verify:
  `uv run mkdocs build --strict` exits 0. — Done: `--strict` build clean;
  MathJax via `docs/site-src/javascripts/mathjax.js` + CDN. Mermaid custom fence dropped (see 3.3 / design D7) so the `!!python/name` tag no longer breaks `check-yaml`.

## 3. Content pages

- [x] 3.1 `docs/site-src/index.md` — what `mlb-research` is, the `pip install
  mlb-research` line, and links to the HF dataset, `/query/`, and the GitHub
  repo. Verify: links resolve under `mkdocs build --strict` (no warnings).
- [x] 3.2 Add `<!-- --8<-- [start:backbone] -->` / `<!-- --8<-- [end:backbone] -->`
  markers around section 3 of `docs/DATA_DICTIONARY.md`; create
  `docs/site-src/data-dictionary.md` that snippet-includes
  `DATA_DICTIONARY.md:backbone` plus a one-paragraph intro and a link to the
  full catalog on GitHub. Verify: `mkdocs build --strict` renders the ten
  backbone tables on the page; deleting a marker fails the build.
- [x] 3.3 `docs/site-src/grain-ladder.md` — a hand-authored inline `<svg>`
  (theme-aware via `currentColor`, no JS/CDN — see design D7) of
  game -> season (stint) -> season (combined) -> team-season -> career, plus
  prose that rates are recomputed from numerators/denominators and never
  averaged. Verify: `<svg>` with every grain label present in the built HTML;
  browser check confirms it renders (5 rects / 18 texts / 5 paths, fill from
  `var(--md-default-fg-color)`).
- [x] 3.4 `docs/site-src/formulas.md` — a table of every metric the project
  publishes with its formula (arithmatex math) and the published source it is
  cited to; ends with a link to `docs/THEORY_AND_METHODOLOGY.md` on GitHub.
  Cross-check the metric list against `docs/FEATURE_REGISTRY.md` /
  `docs/THEORY_AND_METHODOLOGY.md` so none is missing. Verify: every row has a
  non-empty citation; `--strict` build clean.
- [x] 3.5 `docs/site-src/limitations.md` — coverage boundaries, regular-season-only
  scope (ADR-283), current Baseball-Reference tie-out tolerances, the
  "missing measurement is not zero" rule; ends with a link to `docs/RESEARCH.md`.
  Verify: content matches the HF dataset card's honest-limitations link target;
  `--strict` build clean.

## 4. CI

- [x] 4.1 Update `.github/workflows/pages.yml`: replace the raw-upload step with
  checkout → `astral-sh/setup-uv` → `uv sync --extra docs` →
  `uv run mkdocs build --strict` → `upload-pages-artifact` from `docs/site`.
  Update `on.push.paths` to `docs/site-src/**`, `mkdocs.yml`, `pyproject.toml`,
  `uv.lock`, `.github/workflows/pages.yml`. Update the header comment. Verify:
  `actionlint` clean; the workflow YAML parses.
- [x] 4.2 Add a `docs-build` job (or extend the existing `lint`/`test` workflow)
  that runs `uv run mkdocs build --strict` on PRs touching `docs/site-src/**` or
  `mkdocs.yml`, so a broken docs build is caught before merge, not only on the
  Pages deploy. Verify: the job runs `mkdocs build --strict` and fails on a
  deliberately broken link.

## 5. Query-page passthrough guard

- [x] 5.1 Add a test (pytest, `tests/` — mkdocs invoked as a subprocess, skipped
  when `mkdocs` is not importable) that runs `mkdocs build` into a temp dir and
  asserts `query/index.html` and `query/query.js` in the output are byte-identical
  to the sources in `docs/site-src/query/`. Verify: red-green — rename the source
  `query.js`, watch it fail; restore, watch it pass.

## 6. Docs + roadmap

- [x] 6.1 `docs/DECISIONS.md` — new ADR recording the `docs/site-src` source /
  `docs/site` generated-output split and the single-workflow build-in-Pages
  decision. Verify: ADR number is the next free one; `openspec validate --strict`
  unaffected.
- [x] 6.2 `openspec/project.md` — mark NOW #5's MkDocs-site half done (leave the
  `understand-anything` half open) and check off the "MkDocs Material docs site
  published" clause in "v1 is done when". Verify: the two mentions are
  consistent; no other NOW item contradicted.
- [x] 6.3 `README.md` — add the published docs-site URL next to the existing
  HF-dataset / query-page links. Verify: link present; `link-check` workflow
  passes (or the URL is allowlisted until first deploy).

## 7. Verification

- [x] 7.1 `uv run mkdocs build --strict` from a clean `uv sync --extra docs`
  produces `docs/site/` with all five pages + `query/`; `mkdocs serve` renders
  the Mermaid diagram and the formula math in a browser (screenshot in the PR).
- [x] 7.2 Full pre-commit + `openspec validate --strict mkdocs-docs-site` +
  `actionlint` on `pages.yml` all clean.
- [x] 7.3 Confirm `git status` is clean of `docs/site/` after a build (gitignore
  works) and that `docs/site-src/query/` is the only tracked copy of the query
  page.

---

### Implementation notes / deviations

- **3.2** A removed `[end:backbone]` marker does NOT fail `mkdocs build --strict`
  (`pymdownx.snippets` reads to EOF and would splice the internal schema onto the
  public page). Guarded instead by `test_docs_site.py::
  test_data_dictionary_page_does_not_leak_the_internal_schema` (red-green
  verified). Two repo-relative links inside section 3 of `DATA_DICTIONARY.md`
  were rewritten to absolute GitHub URLs so `--strict` passes.
- **3.4** Formula math uses inline `\( \)`, not block `\[ \]` — block math does
  not render inside a Markdown table cell. `arithmatex` (generic) + MathJax 3.
- **6.1** ADR is **286**, not the next-free 285: `odds-update-cron` (PR, in
  review) already claims 285. Noted in the ADR body.
- **6.2** NOW #5 updated to reflect the site is built (PR open); the "v1 is done
  when … MkDocs Material docs site published" clause was left unchecked because
  the site is not deployed until this merges — marking it now would be false per
  the verification rules.
- **6.3** No `lychee` allowlist needed: the PR link-check runs `--offline`
  advisory; the blocking weekly run is post-merge, by which time Pages has
  deployed the URL.

### Verification evidence (7.x)

- **7.1** Clean `uv sync --frozen --extra docs` + `mkdocs build --strict` -> all
  5 pages + `query/` passthrough. `mkdocs serve` + agent-browser: every page
  loads 200 with the right title/h1; the grain-ladder `<svg>` renders (5 rects,
  18 `<text>`, 5 `<path>`, text fill `rgba(0,0,0,0.87)` from
  `var(--md-default-fg-color)`); the formulas page typesets 28 `mjx-container`
  elements. No screenshot captured (headless env), render verified via DOM.
- **7.2** `openspec validate --strict mkdocs-docs-site` = valid;
  `openspec validate --all` 5 passed / 0 failed; full `pre-commit run` all
  Passed; `actionlint` (docker) exit 0 on `pages.yml` + `ci.yml`.
- **7.3** `git status --porcelain docs/site/` empty after a build;
  `git check-ignore docs/site/index.html` matches; `git ls-files` shows only
  `docs/site-src/query/*` as the tracked query page.
