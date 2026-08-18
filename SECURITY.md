# Security policy

## Reporting a vulnerability

Please use GitHub's private vulnerability-reporting flow for this repository.
If it is unavailable, contact the maintainer privately through their GitHub
profile. Do not publish a security issue, credential, database URL, production
data dump, private record, copied third-party content, unlicensed source data,
or reproduction data containing secrets in a public issue, pull request,
commit, Discussion, fixture, or example.

Include a concise description, the affected revision or path, reproduction
steps, impact, and any suggested mitigation. We will acknowledge a good-faith
report and work on a fix before public disclosure.

## Secret handling

- Keep credentials only in environment variables or ignored local `.env` files.
- Never commit API keys, database URLs with passwords, private keys, access
  tokens, session files, or agent-specific configuration containing credentials.
- Never attach production dumps, private records, copied third-party material,
  or unlicensed source data to a public issue, pull request, Discussion,
  fixture, or example.
- Run `uv run pre-commit run --all-files` before opening a pull request. The
  Gitleaks hook blocks common secrets locally; GitHub secret scanning and push
  protection are the server-side backstop.
- If a secret may have been exposed, revoke or rotate it first, then report it
  privately. Removing it in a later commit does not remove it from Git history.

## Data and database safety

`mlb` is production data. `mlb_test` is the only database that tests may use.
Do not use production credentials in CI, test fixtures, issue attachments, or
example commands.
