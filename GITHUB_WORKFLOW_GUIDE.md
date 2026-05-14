# GitHub Workflow Guide for Baseball Analytics Platform

This document outlines the standardized GitHub workflow for the baseball analytics platform, ensuring consistency, quality, and traceability in all development activities.

## Table of Contents
1. [Branching Strategy](#branching-strategy)
2. [Tagging Strategy](#tagging-strategy)
3. [Issue Management](#issue-management)
4. [Pull Request Process](#pull-request-process)
5. [CI/CD Pipeline](#cicd-pipeline)
6. [Documentation Standards](#documentation-standards)
7. [Code Review Guidelines](#code-review-guidelines)
8. [Release Process](#release-process)
9. [Metrics & Tracking](#metrics--tracking)

---

## 1. Branching Strategy

We follow a GitFlow-inspired branching model:

### Permanent Branches
- **`main`**: Production-ready code only. Always deployable.
- **`develop`**: Integration branch for features. Contains latest delivered development changes.

### Temporary Branches
- **`feature/*`**: New features (branch off `develop`, merge back to `develop`)
  - Naming: `feature/<issue-number>-short-description`
  - Example: `feature/123-add-espn-ingestor`
  
- **`bugfix/*`**: Bug fixes (branch off `develop`, merge to `develop` and `main`)
  - Naming: `bugfix/<issue-number>-short-description`
  - Example: `bugfix/456-fix-mlb-ingestor-tables`
  
- **`release/*`**: Release preparation (branch off `develop`, merge to `main` and `develop`)
  - Naming: `release/v<version>` (e.g., `release/v0.2.0`)
  
- **`hotfix/*`**: Critical production fixes (branch off `main`, merge to `main` and `develop`)
  - Naming: `hotfix/<issue-number>-short-description`
  
- **`docs/*`**: Documentation changes
  - Naming: `docs/<issue-number>-short-description`

### Branch Protection Rules
Protected branches (`main` and `develop`) require:
- Pull request reviews before merging
- Status checks to pass before merging
- Linear history (no merge commits, or allow merge commits)
- Administrators included
- Conversation resolution before merging

---

## 2. Tagging Strategy

### Version Tags
- **Format**: `v<MAJOR>.<MINOR>.<PATCH>` (Semantic Versioning)
- **Examples**: `v0.1.0`, `v0.2.0`, `v1.0.0`
- **Applied to**: `main` branch after releases

### Milestone Tags
- **Format**: `milestone-<description>`
- **Examples**: `milestone-raw-ingestion-complete`, `milestone-feature-engineering-start`
- **Purpose**: Mark significant development milestones

### Release Tags
- Same as version tags, applied when creating GitHub releases
- Include release notes generated from PRs since last release

---

## 3. Issue Management

### Issue Types (Labels)
- `type: bug` - Something isn't working
- `type: feature` - New feature request
- `type: enhancement` - Improvement to existing functionality
- `type: documentation` - Docs improvements
- `type: task` - Work that needs to be done
- `type: question` - Questions needing answers

### Priority Labels
- `priority: high` - Must fix soon
- `priority: medium` - Should fix
- `priority: low` - Nice to have

### Area Labels (by project structure)
- `area: download`
- `area: ingest`
- `area: features`
- `area: models`
- `area: predict`
- `area: db`
- `area: cli`
- `area: testing`
- `area: documentation`

### Issue Templates
Stored in `.github/ISSUE_TEMPLATE/`:
- `bug_report.md`
- `feature_request.md`
- `task.md`
- `question.md`

### Using Issues as Canonical Task Source
1. All work starts as an issue
2. Issues are prioritized and added to milestones
3. Work begins only when issue is assigned and in progress
4. Progress tracked through issue updates, PR links, and checklists
5. Issue closed only when associated PR is merged and acceptance criteria met

---

## 4. Pull Request Process

### PR Requirements
1. **Branch**: Create from `develop` for features, `main` for hotfixes
2. **Naming**: Follow branch naming conventions above
3. **Size**: Keep PRs small and focused (ideally <400 lines changed)
4. **Description**: Must include:
   - Summary of changes
   - Related issue number (Closes #xxx or Fixes #xxx)
   - Testing performed
   - Screenshots if UI changes
   - Any breaking changes or migration notes
5. **Checks**:
   - All tests must pass
   - Code coverage thresholds met
   - Linting/formatting passes
   - Security scans pass
6. **Review**:
   - Minimum 1 approving review (2 for complex changes)
   - Address all review comments
   - Use suggested changes feature when appropriate
7. **Merging**:
   - Use squash and merge for feature branches (keeps history clean)
   - Use merge commit for releases if desired
   - Delete branch after merge

### PR Template
Stored in `.github/PULL_REQUEST_TEMPLATE.md`:
- Summary
- Related Issue
- Type of change
- Testing Performed
- Checklist

---

## 5. CI/CD Pipeline

### GitHub Actions Workflows
Located in `.github/workflows/`:

#### `ci.yml` - Continuous Integration
- Runs on push and PR to `main` and `develop`
- Steps:
  1. Checkout code
  2. Set up Python 3.12
  3. Install dependencies
  4. Lint with ruff
  5. Type check with pyright
  6. Run tests with coverage
  7. Upload coverage to Codecov

#### `release.yml` - Release Automation
- Triggered on tag push to `main`
- Steps:
  1. Checkout code
  2. Set up Python
  3. Install dependencies
  4. Run tests
  5. Build package
  6. Create GitHub release
  7. Publish to PyPI (if applicable)

### Branch Protection
Enabled for `main` and `develop` branches:
- Require pull request reviews
- Require status checks
- Require linear history
- Include administrators
- Require conversation resolution

---

## 6. Documentation Standards

### README.md
- Clear project overview
- Installation instructions
- Quick start guide
- Architecture overview
- API usage examples
- Contributing guidelines

### CONTRIBUTING.md
- How to report bugs
- How to suggest features
- Development setup instructions
- Coding standards
- Pull request process
- License information

### CHANGELOG.md
- Keep updated with notable changes
- Follow Keep a Changelog format
- Update in PRs that add user-facing changes

### Inline Documentation
- Follow PEP 257 for docstrings
- Use type hints where practical
- Comment complex logic
- Keep documentation updated with code changes

---

## 7. Code Review Guidelines

### What to Look For
1. **Correctness**: Does the code work as intended?
2. **Clarity**: Is the code easy to understand?
3. **Maintainability**: Is the code easy to modify and extend?
4. **Patterns**: Does it follow established project patterns?
5. **Tests**: Are there adequate tests that pass?
6. **Documentation**: Is documentation updated if needed?
7. **Performance**: Are there obvious performance issues?
8. **Security**: Are there security vulnerabilities?

### Review Process
1. Reviewer examines code against guidelines
2. Leaves comments and suggestions
3. Author addresses all feedback
4. Reviewer approves when satisfied
5. Maintainer merges after approval and passing checks

### Review Etiquette
- Be respectful and constructive
- Focus on code, not author
- Provide specific, actionable feedback
- Acknowledge good practices
- Use GitHub's suggestion feature when appropriate

---

## 8. Release Process

### Pre-Release Checklist
1. All issues in milestone are closed
2. Main branch is stable and tested
3. Documentation is up to date
4. CHANGELOG.md updated
5. Version number determined

### Release Steps
1. Create release branch: `git checkout -b release/vX.Y.Z develop`
2. Update version numbers in code (if applicable)
3. Update CHANGELOG.md with release notes
4. Commit changes: `git commit -m "chore: prepare release vX.Y.Z"`
5. Push branch and create PR to main
6. Get required approvals
7. Merge PR to main (creates merge commit)
8. Tag release: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`
9. Push tag: `git push origin vX.Y.Z`
10. Merge main back to develop: `git checkout develop && git merge main`
11. Delete release branch
12. GitHub Actions automatically creates GitHub release

### Post-Release
- Announce release to stakeholders
- Monitor for issues
- Begin work on next milestone

---

## 9. Metrics & Tracking

### Key Metrics to Monitor
1. **Issue Lead Time**: Time from issue creation to closure
2. **PR Cycle Time**: Time from PR open to merge
3. **Issue-to-PR Ratio**: Percentage of issues with associated PRs
4. **Test Coverage**: Percentage of code covered by tests
5. **Build Success Rate**: Percentage of CI runs that pass
6. **Release Frequency**: How often releases occur

### Tracking Methods
- GitHub Insights and Analytics
- Project boards (GitHub Projects)
- Milestone progress tracking
- Regular retrospectives (monthly or quarterly)
- Team feedback and continuous improvement

---

## Implementation Notes

### For Maintainers
- Enforce branch protection rules
- Review PRs promptly (within 2 business days)
- Keep documentation up to date
- Foster positive, collaborative environment
- Continuously improve the workflow based on feedback

### For Contributors
- Read CONTRIBUTING.md before starting work
- Follow branching and naming conventions
- Write tests for new functionality
- Keep PRs focused and well-documented
- Respond to review feedback promptly
- Squash commits before merging if requested

### Getting Started
1. Clone repository: `git clone https://github.com/yourusername/baseball.git`
2. Install dependencies: `pip install -e .[dev]`
3. Copy `.env.example` to `.env` and configure
4. Create feature branch: `git checkout -b feature/issue-number-description`
5. Work on task with regular commits
6. Push branch and open PR when ready
7. Link PR to issue in description
8. Address review feedback
9. Merge when approved

---

This workflow ensures that our development process is transparent, quality-focused, and scalable. By following these guidelines, we maintain a clean history, ensure code quality through review and testing, and provide clear traceability from issues to code changes.