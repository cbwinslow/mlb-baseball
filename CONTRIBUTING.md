# Contributing to Baseball Analytics Platform

Thank you for considering contributing to our project! Please read this guide to understand how to contribute effectively.

## How to Contribute

### Reporting Bugs
- Use the bug report issue template
- Include steps to reproduce, expected vs actual behavior
- Add relevant logs or screenshots

### Suggesting Features
- Use the feature request issue template
- Clearly describe the problem and proposed solution
- Consider alternatives and trade-offs

### Making Code Changes
1. Fork the repository
2. Create a branch from `develop`: `git checkout -b feature/issue-number-description`
3. Make your changes following our coding standards
4. Add or update tests as needed
5. Ensure all tests pass locally
6. Commit your changes with descriptive messages
7. Push to your fork and open a pull request

### Pull Request Process
1. Fill out the pull request template completely
2. Link to related issue using "Closes #xxx" or "Fixes #xxx"
3. Request review from at least one maintainer
4. Address all review comments
5. Once approved, maintainers will squash and merge
6. Your branch will be deleted after merge

## Coding Standards
- Follow PEP 8 with line length of 88 characters (Black formatting)
- Use type hints where practical
- Write descriptive docstrings for public functions
- Keep functions focused and small (<50 lines when possible)
- Handle exceptions appropriately
- Write unit tests for new functionality
- Update documentation when changing interfaces

## Development Setup
1. Clone the repository: `git clone https://github.com/yourusername/baseball.git`
2. Install dependencies: `pip install -e .[dev]`
3. Set up PostgreSQL database
4. Copy `.env.example` to `.env` and configure
5. Run tests: `pytest`

## GitHub Workflow
Please see [GITHUB_WORKFLOW_GUIDE.md](GITHUB_WORKFLOW_GUIDE.md) for detailed information about our branching strategy, issue management, pull request process, CI/CD pipeline, and release procedures.

## Getting Help
If you need help, please:
1. Check the documentation in the `docs/` directory
2. Look through existing issues and pull requests
3. Ask questions in the issue tracker
4. Reach out to maintainers

We appreciate your contributions!