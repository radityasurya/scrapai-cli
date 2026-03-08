# Dependency Management

This document describes how dependencies are managed in ScrapAI.

## Current Strategy

ScrapAI uses **pinned version ranges** in `requirements.txt` to balance stability with security updates.

### Requirements Files

- `requirements.txt` - Production dependencies with minimum versions
- `requirements-dev.txt` - Development dependencies (testing, linting, security tools)

### Version Pinning Philosophy

We use **minimum version pinning** (e.g., `scrapy>=2.11.0`) rather than exact pinning (e.g., `scrapy==2.11.0`) because:

1. **Security updates** - Allows pip to install security patches
2. **Compatibility** - ScrapAI is a library/tool, not a locked application
3. **Testing coverage** - We test against a range of supported Python versions (3.10-3.13)

### When to Use Exact Pinning

For **production deployments** (Docker, servers), generate a lockfile:

```bash
# Generate lockfile with exact versions
pip freeze > requirements.lock

# Install from lockfile
pip install -r requirements.lock
```

## Security Scanning

### Automated Checks

CI runs automated security checks on every push:

1. **Safety** - Checks for known vulnerabilities in dependencies
2. **Bandit** - Static analysis for Python code security issues

These checks are **non-blocking** but upload reports for review.

### Manual Security Audit

Run security checks locally:

```bash
# Check for vulnerable dependencies
pip install safety
safety check

# Check for code security issues
pip install bandit
bandit -r core spiders cli handlers utils
```

## Updating Dependencies

### Regular Updates

```bash
# Check for outdated packages
pip list --outdated

# Update specific package
pip install --upgrade package-name

# Update requirements.txt if needed
pip freeze | grep package-name >> requirements.txt
```

### Security Updates

When a security vulnerability is reported:

1. Update the affected package: `pip install --upgrade package-name`
2. Test the update: `pytest tests/`
3. Update `requirements.txt` with new minimum version
4. Document in commit message: "security: update package-name for CVE-XXXX"

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
4. Run tests to ensure compatibility

## Dependency Review

Periodically (monthly/quarterly):

1. Run `pip list --outdated`
2. Review security advisories
3. Update dependencies as needed
4. Run full test suite
5. Check for breaking changes in changelogs

## CI/CD Integration

GitHub Actions workflow (`.github/workflows/tests.yml`):

- Tests against Python 3.10, 3.11, 3.12, 3.13
- Runs security scans (Safety, Bandit)
- Uploads security reports as artifacts

## Future Improvements

Potential enhancements:

- [ ] Add `pip-audit` for vulnerability scanning
- [ ] Use Dependabot for automated PRs
- [ ] Generate lockfiles for releases
- [ ] Add dependency update automation
