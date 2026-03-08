# Security Policy

## Recent Security Improvements

### Injection Vulnerabilities (Command Injection)
**Status**: ✅ FIXED
- **Fixed in**: Airflow DAG tasks (`airflow/dags/scrapai_spider_dags.py`)
- **Method**: All user-controlled values now use `shlex.quote()`
- **Severity**: Critical
- **Impact**: Remote code execution on Airflow workers
- **CVE**: N/A (internal fix)

- **Commit**: d9b212f

### Unsafe Deserialization (Pickle)
**Status**: ✅ FIXED
- **Fixed in**: Checkpoint metadata handling (`cli/crawl.py`)
- **Method**: Replaced `pickle.load()` with JSON
- **Severity**: High
- **Impact**: Local code execution if attacker can write checkpoint files
- **CVE**: N/A (internal fix)
- **Commit**: fa1850d

### SSRF Vulnerabilities
**Status**: ✅ FIXED
- **Fixed in**: URL inspection commands (`cli/inspect_cmd.py`, `utils/inspector.py`)
- **Method**: Added URL validation for localhost/private IPs
- **Severity**: High
- **Impact**: Internal network access, metadata service leakage
- **CVE**: N/A (internal fix)
- **Commit**: fa1850d

### Sensitive Data Exposure (Credentials)
**Status**: ✅ FIXED
- **Fixed in**: Database transfer output (`cli/db.py`)
- **Method**: Redact passwords from connection strings
- **Severity**: Medium
- **Impact**: Credential leakage in logs
- **CVE**: N/A (internal fix)
- **Commit**: fa1850d

### Insecure Defaults (Admin Credentials)
**Status**: ✅ FIXED
- **Fixed in**: Airflow Docker setup (`docker-compose.airflow.yml`)
- **Method**: Removed admin/admin defaults, require explicit credentials
- **Severity**: High
- **Impact**: Unauthorized access to Airflow UI
- **CVE**: N/A (internal fix)
- **Commit**: d9b212f

## Current Security Posture

After the security audit, the following improvements have been implemented:

1. **Shell Injection Protection**: All user-controlled values in shell commands are safely quoted
2. **Safe Deserialization**: Pickle deserialization replaced with JSON
3. **SSRF Protection**: URL inspection commands validate URLs before fetching
4. **Credential Redaction**: Database credentials are redacted in CLI output
5. **Secure Defaults**: Airflow setup requires explicit admin credentials
6. **CI Security Enforcement**: Security scans fail on HIGH severity issues

## Reporting a Vulnerability


**Please DO NOT report security vulnerabilities through public GitHub issues.**

Email us directly: **dev@discourselab.ai**

Include:
1. Type of vulnerability (SQL injection, command injection, SSRF, etc.)
2. Affected component (CLI command, spider, handler)
3. Steps to reproduce
4. Impact assessment

We'll acknowledge within 72 hours and work with you on a fix.

## Scope

### In Scope

- Injection vulnerabilities (SQL, command, code)
- Path traversal / directory access
- Remote code execution
- Sensitive data exposure
- Server-side request forgery (SSRF)
- Insecure defaults

### Out of Scope

- Web scraping ethics (scraping public websites is not a vulnerability)
- Cloudflare bypass techniques (core feature, not a bug)
- Robots.txt violations (user responsibility)
- Outdated dependencies (unless actively exploitable)

## Safe Harbor

We will not pursue legal action against researchers who act in good faith, do not exploit vulnerabilities beyond proof-of-concept, and give us reasonable time to fix before public disclosure.

We will publicly acknowledge your contribution unless you prefer anonymity.

## Questions

📧 **dev@discourselab.ai**
