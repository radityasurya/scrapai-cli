# Contributing to ScrapAI

Thanks for your interest in contributing! This guide will help you get started.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
- [Code Style](#code-style)
- [Testing](#testing)
- [Git Hooks](#git-hooks)
- [Pull Request Process](#pull-request-process)
- [Reporting Issues](#reporting-issues)

## Code of Conduct

Be respectful, inclusive, and constructive. We welcome contributions from everyone.

## Development Setup

### Prerequisites

- Python 3.9+ (3.11+ recommended)
- Git
- Virtual environment (venv, conda, or similar)

### Quick Start

```bash
# Clone the repository
git clone https://github.com/discourselab/scrapai-cli.git
cd scrapai-cli

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install Playwright browsers
playwright install chromium

# Copy environment file
cp .env.example .env

# Install git hooks (recommended)
make hooks-install
```

### Verify Installation

```bash
# Run tests
make test

# Check code style
make lint

# Run a quick test
./scrapai --help
```

## Project Structure

```
scrapai-cli/
├── api/                 # REST API (FastAPI)
│   ├── routers/         # API endpoints
│   ├── main.py          # FastAPI app
│   └── config.py        # API configuration
├── cli/                 # CLI commands
├── core/                # Core functionality
│   ├── db.py            # Database models
│   ├── config.py        # Configuration loading
│   └── spider.py        # DatabaseSpider
├── docs/                # Documentation
├── handlers/            # Scrapy handlers (Cloudflare, etc.)
├── services/            # Background services (Redis, Dramatiq)
├── spiders/             # Spider templates
├── templates/           # Project templates
├── tests/               # Test suite
│   ├── unit/            # Unit tests
│   └── integration/     # Integration tests
├── utils/               # Utility functions
├── workers/             # Background workers
├── middlewares.py       # Scrapy middlewares
├── pipelines.py         # Scrapy pipelines
├── settings.py          # Scrapy settings
└── scrapai              # CLI entry point
```

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-number
```

### 2. Make Changes

- Write clean, documented code
- Follow the existing code style
- Add tests for new functionality
- Update documentation if needed

### 3. Test Your Changes

```bash
# Run all tests
make test

# Run specific test file
pytest tests/unit/test_spider.py -v

# Run with coverage
make test-coverage
```

### 4. Check Code Quality

```bash
# Format code
make format

# Check linting
make lint

# Type checking
make typecheck

# Security scan
make security
```

### 5. Commit Your Changes

We use conventional commits:

```
feat: add new feature
fix: fix bug in spider
docs: update documentation
test: add tests for X
refactor: clean up code
chore: update dependencies
```

### 6. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then create a pull request on GitHub.

## Code Style

### Python

- **Formatter**: Black (line length: 100)
- **Linter**: Flake8
- **Imports**: isort (profile: black)
- **Types**: Type hints encouraged, mypy for checking

```bash
# Format and check
make format
make lint
```

### Key Conventions

- Use **snake_case** for functions and variables
- Use **PascalCase** for classes
- Keep functions focused and small
- Document public functions with docstrings
- Use Pydantic models for data validation

### Example

```python
from typing import Optional
from pydantic import BaseModel


class SpiderConfig(BaseModel):
    """Spider configuration loaded from database."""

    name: str
    allowed_domains: list[str]
    start_urls: list[str]
    rules: Optional[list[dict]] = None

    def get_allowed_domains_string(self) -> str:
        """Return comma-separated allowed domains."""
        return ", ".join(self.allowed_domains)
```

## Testing

### Test Structure

```
tests/
├── unit/              # Fast, isolated tests
│   ├── test_spider.py
│   └── test_config.py
├── integration/       # Slower, full-stack tests
│   └── test_crawl.py
└── fixtures/          # Test data
```

### Running Tests

```bash
# All tests
make test

# Unit tests only (fast)
make test-unit

# Integration tests
make test-integration

# With coverage
make test-coverage

# Watch mode
make test-watch
```

### Writing Tests

```python
import pytest
from core.spider import DatabaseSpider


class TestDatabaseSpider:
    """Tests for DatabaseSpider class."""

    def test_load_config_from_database(self, mock_db):
        """Test loading spider config from database."""
        spider = DatabaseSpider.from_database("test_spider")
        assert spider.name == "test_spider"

    @pytest.mark.parametrize("url,expected", [
        ("https://example.com/article", True),
        ("https://example.com/page/2", False),
    ])
    def test_should_follow(self, url: str, expected: bool):
        """Test URL follow logic."""
        # Test implementation
        pass
```

## Git Hooks

We use pre-commit for automated checks:

```bash
# Install hooks
make hooks-install

# Run manually on all files
make hooks-run

# Update to latest hook versions
make hooks-update
```

### What Gets Checked

- **pre-commit**: Black, isort, flake8, mypy, bandit, unit tests
- **pre-push**: (configured but optional)

## Pull Request Process

1. **Fork & Branch**: Create a feature branch from `main`
2. **Code**: Make your changes with tests
3. **Test**: Ensure all tests pass
4. **Document**: Update docs if needed
5. **Submit**: Open a PR with a clear description

### PR Checklist

- [ ] Tests pass locally
- [ ] Code is formatted (`make format`)
- [ ] No lint errors (`make lint`)
- [ ] Documentation updated (if needed)
- [ ] Commit messages are clear
- [ ] PR description explains the change

### Review Process

1. Automated checks run (CI/CD)
2. At least one maintainer review
3. Address feedback
4. Squash and merge when approved

## Reporting Issues

### Bug Reports

Include:

- ScrapAI version (`./scrapai --version`)
- Python version (`python --version`)
- OS and version
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs (use `--verbose`)

### Feature Requests

Include:

- Use case description
- Proposed solution (if any)
- Alternatives considered

### Security Issues

**Do not open public issues for security vulnerabilities.**

Email: security@discourselab.ai

## Getting Help

- **Documentation**: [docs/](docs/)
- **Discussions**: [GitHub Discussions](https://github.com/discourselab/scrapai-cli/discussions)
- **Issues**: [GitHub Issues](https://github.com/discourselab/scrapai-cli/issues)

---

Thank you for contributing to ScrapAI! 🚀
