# Troubleshooting Guide

Common issues and solutions for ScrapAI.

## Table of Contents

- [Installation Issues](#installation-issues)
- [Spider Problems](#spider-problems)
- [Cloudflare & Anti-Bot](#cloudflare--anti-bot)
- [Proxy Issues](#proxy-issues)
- [Database Errors](#database-errors)
- [API Errors](#api-errors)
- [Performance Issues](#performance-issues)
- [Environment & Configuration](#environment--configuration)

## Installation Issues

### Playwright Installation Fails

**Problem:** `playwright install` fails or browsers don't work.

**Solution:**
```bash
# Install with dependencies
playwright install chromium --with-deps

# On Ubuntu/Debian, you may need:
sudo apt-get install -y libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2

# On macOS with Apple Silicon:
arch -arm64 playwright install chromium
```

### ImportError: No module named 'scrapy'

**Problem:** Module not found even after installation.

**Solution:**
```bash
# Make sure venv is activated
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# Reinstall requirements
pip install -r requirements.txt --force-reinstall
```

### CloakBrowser Installation Fails

**Problem:** `cloakbrowser` dependency issues.

**Solution:**
```bash
# CloakBrowser requires nodriver
pip install nodriver>=0.36

# If still failing, try:
pip install cloakbrowser --no-deps
pip install nodriver playwright
```

## Spider Problems

### Spider Returns No Items

**Problem:** Crawl runs but extracts 0 items.

**Diagnosis:**
```bash
# Check spider health
./scrapai health --project myproject --spider myspider

# Run with verbose output
./scrapai crawl myspider --verbose

# Test URL matching
./scrapai test myspider --url "https://example.com/article"
```

**Solutions:**

1. **Selectors changed** - Site layout updated:
   ```bash
   ./scrapai analyze myspider --update
   ```

2. **Wrong callback** - Links not matching rules:
   ```bash
   # Check rules in spider config
   ./scrapai show myspider --config
   ```

3. **Content in JavaScript** - Need JS rendering:
   ```bash
   # Enable CloakBrowser
   ./scrapai crawl myspider --browser
   ```

### Spider Gets 403/429 Errors

**Problem:** Site returns forbidden or rate limit errors.

**Solutions:**

1. **Enable proxy:**
   ```bash
   # Configure in .env
   DATACENTER_PROXY_USERNAME=user
   DATACENTER_PROXY_PASSWORD=pass
   DATACENTER_PROXY_HOST=proxy.example.com
   DATACENTER_PROXY_PORT=10000

   # Run with proxy
   ./scrapai crawl myspider --proxy
   ```

2. **Reduce concurrency:**
   ```bash
   ./scrapai crawl myspider --concurrency 1 --delay 2
   ```

3. **Enable auto-throttle:**
   ```bash
   # In spider config or globally
   AUTOTHROTTLE_ENABLED=true
   ```

### DeltaFetch Not Skipping Seen Pages

**Problem:** Re-crawling already visited URLs.

**Solutions:**

```bash
# Check DeltaFetch is enabled
grep DELTAFETCH settings.py

# Reset DeltaFetch cache
rm -rf .scrapy/deltafetch/

# Disable for testing
./scrapai crawl myspider --no-deltafetch
```

## Cloudflare & Anti-Bot

### Cloudflare Challenge Loop

**Problem:** Stuck in Cloudflare challenge, spider times out.

**Solutions:**

1. **Enable CloakBrowser:**
   ```bash
   ./scrapai crawl myspider --browser
   ```

2. **Increase timeout:**
   ```bash
   ./scrapai crawl myspider --browser --timeout 120
   ```

3. **Use residential proxy:**
   ```bash
   # In .env
   RESIDENTIAL_PROXY_USERNAME=user
   RESIDENTIAL_PROXY_PASSWORD=pass

   ./scrapai crawl myspider --proxy --proxy-type residential
   ```

### "Please enable JavaScript" Error

**Problem:** Page requires JavaScript but spider doesn't render it.

**Solution:**
```bash
# Use browser mode
./scrapai crawl myspider --browser

# Or use Playwright extractor
./scrapai analyze myspider --extractor playwright
```

### Bot Detection Even With CloakBrowser

**Problem:** Still getting blocked despite using CloakBrowser.

**Solutions:**

1. **Rotate user agents** (automatic in ScrapAI)

2. **Use residential proxies:**
   ```bash
   ./scrapai crawl myspider --browser --proxy-type residential
   ```

3. **Add delays:**
   ```bash
   ./scrapai crawl myspider --delay 3
   ```

4. **Check if IP is blacklisted:**
   ```bash
   curl -s https://ipinfo.io/json | jq .
   ```

## Proxy Issues

### Proxy Connection Refused

**Problem:** `ProxyError: 407 Proxy Authentication Required`

**Solutions:**

```bash
# Check credentials in .env
cat .env | grep PROXY

# Test proxy connection
curl -x "http://user:pass@host:port" https://api.ipify.org

# Common SmartProxy format
DATACENTER_PROXY_HOST=gate.smartproxy.com
DATACENTER_PROXY_PORT=10000  # Rotating
```

### Proxy Not Being Used

**Problem:** Spider doesn't use configured proxy.

**Solutions:**

1. **Check middleware is enabled:**
   ```python
   # In settings.py
   DOWNLOADER_MIDDLEWARES = {
       "middlewares.SmartProxyMiddleware": 350,
   }
   ```

2. **Force proxy for specific spider:**
   ```bash
   ./scrapai crawl myspider --force-proxy
   ```

3. **Check all proxy vars are set:**
   ```bash
   # All 4 must be set
   DATACENTER_PROXY_USERNAME=xxx
   DATACENTER_PROXY_PASSWORD=xxx
   DATACENTER_PROXY_HOST=xxx
   DATACENTER_PROXY_PORT=xxx
   ```

## Database Errors

### "Database is locked" (SQLite)

**Problem:** SQLite database locks during concurrent access.

**Solutions:**

```bash
# Option 1: Close other connections
pkill -f scrapai

# Option 2: Use WAL mode
sqlite3 scrapai.db "PRAGMA journal_mode=WAL;"

# Option 3: Switch to PostgreSQL
DATABASE_URL=postgresql://user:pass@localhost:5432/scrapai
```

### Connection Refused (PostgreSQL)

**Problem:** `psycopg2.OperationalError: could not connect to server`

**Solutions:**

```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check connection string
echo $DATABASE_URL

# Test connection
psql "$DATABASE_URL" -c "SELECT 1"

# Check pg_hba.conf allows connections
sudo vim /etc/postgresql/*/main/pg_hba.conf
```

### Alembic Migration Fails

**Problem:** `alembic upgrade head` fails.

**Solutions:**

```bash
# Check current revision
alembic current

# See migration history
alembic history

# Mark as complete (if already applied)
alembic stamp head

# Reset migrations (WARNING: loses data)
alembic downgrade base
alembic upgrade head
```

## API Errors

### Redis Connection Error

**Problem:** API fails with `redis.exceptions.ConnectionError`

**Solutions:**

```bash
# Check Redis is running
redis-cli ping

# Check Redis config
cat .env | grep REDIS

# Test connection
redis-cli -h localhost -p 6379 ping
```

### "Rate limit exceeded"

**Problem:** API returns 429 Too Many Requests.

**Solutions:**

```bash
# Check rate limit settings (in API config)
# Default: 100 requests/minute

# Wait and retry
# Or increase limit for your use case
```

### 500 Internal Server Error

**Problem:** API returns 500 error.

**Diagnosis:**
```bash
# Check logs
tail -f logs/api.log

# Run with debug
uvicorn api.main:app --reload --log-level debug
```

## Performance Issues

### Crawl Too Slow

**Problem:** Spider crawling very slowly.

**Solutions:**

```bash
# Increase concurrency
./scrapai crawl myspider --concurrency 16

# Disable AutoThrottle (if appropriate)
AUTOTHROTTLE_ENABLED=false

# Reduce delay
./scrapai crawl myspider --delay 0.5
```

### Memory Usage High

**Problem:** Spider using too much memory.

**Solutions:**

1. **Enable checkpointing:**
   ```bash
   ./scrapai crawl myspider --checkpoint --batch-size 1000
   ```

2. **Reduce cache:**
   ```python
   HTTPCACHE_ENABLED = False
   ```

3. **Clear deltafetch:**
   ```bash
   rm -rf .scrapy/deltafetch/
   ```

### High CPU Usage

**Problem:** Spider consuming too much CPU.

**Solutions:**

1. **Disable不必要的日志:**
   ```python
   LOG_LEVEL = "WARNING"
   ```

2. **Use simpler extractors:**
   ```bash
   ./scrapai analyze myspider --extractor newspaper
   # vs
   ./scrapai analyze myspider --extractor trafilatura
   ```

## Environment & Configuration

### .env Not Loading

**Problem:** Environment variables not being read.

**Solutions:**

```bash
# Check .env exists
ls -la .env

# Check format (no spaces around =)
DATA_DIR=./data  # Correct
DATA_DIR = ./data  # Wrong

# Load manually
source .env  # bash
```

### SECRET_KEY Warning

**Problem:** "Using default SECRET_KEY" warning.

**Solution:**
```bash
# Generate secure key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Add to .env
SECRET_KEY=your-generated-key-here
```

### Wrong Python Version

**Problem:** Features not working with older Python.

**Solution:**
```bash
# Check version
python --version  # Need 3.9+

# Use specific version
python3.11 -m venv venv
```

## Getting More Help

1. **Enable verbose logging:**
   ```bash
   ./scrapai crawl myspider --verbose --log-level DEBUG
   ```

2. **Check existing issues:** [GitHub Issues](https://github.com/discourselab/scrapai-cli/issues)

3. **Ask in discussions:** [GitHub Discussions](https://github.com/discourselab/scrapai-cli/discussions)

4. **Create a bug report** with:
   - Full error message
   - ScrapAI version
   - Python version
   - OS
   - Minimal reproduction steps
