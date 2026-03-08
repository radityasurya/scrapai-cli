# Dependency Management

This document describes how dependencies are managed in ScrapAI.

## Dual Strategy Approach

ScrapAI uses a **dual dependency management strategy** to balance development flexibility with production stability:

### 1. Development/Testing: Minimum Version Pinning

For `requirements.txt` and `requirements-dev.txt`, we use **minimum version pinning** (e.g., `scrapy>=2.11.0`):

**Benefits:**
- ✅ Allows security patches to be installed automatically
- ✅ Tests against a range of compatible versions
- ✅ Ensures CI runs with latest compatible dependencies
- ✅ Catches compatibility issues early

**When to use:**
- Local development
- CI/CD pipelines
- Testing new features

### 2. Production Deployment: Exact Version Locking

For production deployments, use **exact version locking** (e.g., `scrapy==2.11.0`):

**Benefits:**
- ✅ Guarantees exact same versions across all environments
- ✅ Prevents unexpected breakage from dependency updates
- ✅ Enables reproducible builds
- ✅ Allows staged rollouts of dependency updates

**When to use:**
- Docker builds
- Server deployments
- Airflow DAG deployments
- Any production environment

## Requirements Files

- `requirements.txt` - Production dependencies with minimum versions
- `requirements-dev.txt` - Development dependencies (testing, linting, security tools)
- `requirements.lock` - Exact versions for production (generated, not committed)

### Version Pinning Philosophy

We use **minimum version pinning** (e.g., `scrapy>=2.11.0`) rather than exact pinning (e.g., `scrapy==2.11.0`) because:

1. **Security updates** - Allows pip to install security patches
2. **Compatibility** - ScrapAI is a library/tool, not a locked application
3. **Testing coverage** - We test against a range of supported Python versions (3.10-3.13)

## Generating Lockfiles

### For Production Deployment

```bash
# Generate lockfile with exact versions
pip freeze > requirements.lock

# Install from lockfile in production
pip install -r requirements.lock
```

### Automated Lockfile Generation

We've provided a helper script for lockfile generation:

```bash
# Generate lockfile (Linux/macOS)
./scripts/generate-lockfile.sh

# Or manually on Windows
pip freeze > requirements.lock
```

### Validation

To validate lockfiles are working correctly:

```bash
# Test installation from lockfile
python -m venv test-env
source test-env/bin/activate  # On Windows: test-env\Scripts\activate
pip install -r requirements.lock
python -c "import scrapy; print(scrapy.__version__)"
deactivate
rm -rf test-env  # On Windows: rmdir /s test-env
```

## CI/CD Integration

### GitHub Actions Workflow

Our CI pipeline (`.github/workflows/tests.yml`) validates both strategies:

1. **Tests against Python 3.10, 3.11, 3.12, 3.13** - Ensures compatibility
2. **Security scans** - Checks for vulnerabilities with Safety and Bandit
3. **Linting** - Enforces code quality standards
4. **Type checking** - Validates type hints

### Security Scanning

CI runs automated security checks on every push:

1. **Safety** - Checks for known vulnerabilities in dependencies
2. **Bandit** - Static analysis for Python code security issues

These checks **fail on HIGH severity issues** and upload reports for review.

## Updating Dependencies

### Regular Updates

```bash
# Check for outdated packages
pip list --outdated

# Update specific package
pip install --upgrade package-name

# Test the update
pytest tests/

# Update requirements.txt if needed
pip freeze | grep package-name >> requirements.txt
```

### Security Updates

When a security vulnerability is reported:

1. Update the affected package: `pip install --upgrade package-name`
2. Test the update: `pytest tests/`
3. Update `requirements.txt` with new minimum version
4. Document in commit message: "security: update package-name for CVE-XXXX"
5. Generate new lockfile for production: `pip freeze > requirements.lock`

## Adding New Dependencies

Before adding a new dependency:

1. **Check alternatives** - Is there a stdlib option? A lighter alternative?
2. **Check maintenance** - Is the package actively maintained?
3. **Check license** - Is it compatible with Apache 2.0?
4. **Check dependencies** - Does it pull in many transitive dependencies?

### Process

1. Add to `requirements.txt` (production) or `requirements-dev.txt` (dev only)
2. Specify minimum version: `package>=1.0.0`
3. Document why it's needed in commit message
4. Run tests to ensure compatibility: `pytest tests/`
5. Generate lockfile if deploying: `pip freeze > requirements.lock`

## Dependency Review

Periodically (monthly/quarterly):

1. Run `pip list --outdated`
2. Review security advisories
3. Update dependencies as needed
4. Run full test suite
5. Check for breaking changes in changelogs
6. Generate new lockfile

## Troubleshooting

### "Package conflicts during installation"

```bash
# Clear pip cache
pip cache purge

# Create fresh virtual environment
python -m venv fresh-env
source fresh-env/bin/activate
pip install -r requirements.txt
```

### "Tests fail with new dependency version"

```bash
# Pin to last known working version temporarily
pip install package==1.2.3

# Investigate breaking changes
# Update code to work with new version
# Update requirements.txt
```

### "Lockfile installation fails"

```bash
# Regenerate lockfile
pip freeze > requirements.lock

# Validate format
head -20 requirements.lock
```

## Future Improvements

Potential enhancements:

- [ ] Add `pip-audit` for vulnerability scanning
- [ ] Use Dependabot for automated PRs
- [ ] Add lockfile freshness check to CI
- [ ] Create pre-commit hook for dependency updates
- [ ] Add dependency update automation
- [ ] Document upgrade testing procedure
