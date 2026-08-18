# GitHub governance runbook

This repository welcomes public, fork-based pull requests. Contributors need a
GitHub account, not direct repository access. Write access is deliberately
restricted to the maintainer so a contributor cannot delete branches, alter
repository settings, or push unreviewed commits to `main`.

## `main` protection

The GitHub branch-protection rule for `main` requires a pull request, the
`test` CI check, and resolution of every review conversation. It applies to
administrators too, prevents force pushes and branch deletion, dismisses stale
reviews after new pushes, and requires the branch to be up to date before merge.

The current review count is zero. This is intentional for a single-maintainer
repository: outside contributors cannot merge their own work, while the owner
can merge a reviewed, passing PR without needing a second account. Increase it
to one once there is a second trusted maintainer.

Only squash merges are enabled, merged head branches are deleted automatically,
and web commits require sign-off.

## Collaboration surfaces

- The public [roadmap project](https://github.com/users/cbwinslow/projects/25)
  contains open, contributor-ready work.
- GitHub Discussions are enabled. Use **Q&A** for setup help, **Ideas** for
  proposals, **General** for collaboration, and **Announcements** for
  maintainer updates. Keep credentials and private data out of all categories.
- Issues are for confirmed bugs and scoped work. Discussions are better for
  exploratory questions and research proposals.

## Security controls

GitHub secret scanning and push protection are enabled. The repository also
runs Gitleaks in pre-commit and CI. These controls reduce accidental exposure;
they do not replace secret rotation when a credential is disclosed.
