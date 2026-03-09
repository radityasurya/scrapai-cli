# Deployment Guide

Production deployment options for ScrapAI.

## Table of Contents

- [Quick Deployment](#quick-deployment)
- [Docker Deployment](#docker-deployment)
- [Manual Deployment](#manual-deployment)
- [Systemd Service](#systemd-service)
- [Nginx Reverse Proxy](#nginx-reverse-proxy)
- [Scaling & Load Balancing](#scaling--load-balancing)
- [Monitoring & Logging](#monitoring--logging)
- [Security Hardening](#security-hardening)
- [Backup & Recovery](#backup--recovery)

## Quick Deployment

### Minimal Setup (SQLite)

```bash
# Install
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your settings

# Initialize database
alembic upgrade head

# Run API
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### Production Setup (PostgreSQL + Redis)

```bash
# 1. Set up PostgreSQL
sudo apt install postgresql postgresql-contrib
sudo -u postgres createuser scrapai -P
sudo -u postgres createdb scrapai -O scrapai

# 2. Set up Redis
sudo apt install redis-server
sudo systemctl enable redis-server

# 3. Configure environment
cat > .env << EOF
DATABASE_URL=postgresql://scrapai:password@localhost:5432/scrapai
REDIS_HOST=localhost
REDIS_PORT=6379
SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4
EOF

# 4. Run with Gunicorn
pip install gunicorn
gunicorn api.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright
RUN playwright install chromium --with-deps

# Copy application
COPY . .

# Create non-root user
RUN useradd -m -u 1000 scrapai && \
    chown -R scrapai:scrapai /app
USER scrapai

# Expose port
EXPOSE 8000

# Run API
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://scrapai:password@db:5432/scrapai
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - SECRET_KEY=${SECRET_KEY}
    depends_on:
      - db
      - redis
    volumes:
      - ./data:/app/data
    restart: unless-stopped

  worker:
    build: .
    command: python -m dramatiq workers.crawl_worker
    environment:
      - DATABASE_URL=postgresql://scrapai:password@db:5432/scrapai
      - REDIS_HOST=redis
      - REDIS_PORT=6379
    depends_on:
      - db
      - redis
    volumes:
      - ./data:/app/data
    restart: unless-stopped

  db:
    image: postgres:15-alpine
    environment:
      - POSTGRES_USER=scrapai
      - POSTGRES_PASSWORD=password
      - POSTGRES_DB=scrapai
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

### Deploy with Docker Compose

```bash
# Set secret key
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# Start services
docker-compose up -d

# Check logs
docker-compose logs -f api

# Run migrations
docker-compose exec api alembic upgrade head
```

## Manual Deployment

### Server Setup (Ubuntu/Debian)

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3.11 python3.11-venv python3-pip \
    postgresql postgresql-contrib redis-server nginx

# Clone repository
git clone https://github.com/discourselab/scrapai-cli.git /opt/scrapai
cd /opt/scrapai

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install gunicorn

# Install Playwright
playwright install chromium --with-deps

# Set up database
sudo -u postgres createuser scrapai -P
sudo -u postgres createdb scrapai -O scrapai

# Configure environment
cp .env.example .env
nano .env  # Edit settings

# Run migrations
alembic upgrade head
```

## Systemd Service

### API Service

```ini
# /etc/systemd/system/scrapai-api.service
[Unit]
Description=ScrapAI API Server
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=scrapai
Group=scrapai
WorkingDirectory=/opt/scrapai
Environment="PATH=/opt/scrapai/venv/bin"
ExecStart=/opt/scrapai/venv/bin/gunicorn api.main:app \
    -w 4 \
    -k uvicorn.workers.UvicornWorker \
    -b 127.0.0.1:8000 \
    --access-logfile /var/log/scrapai/access.log \
    --error-logfile /var/log/scrapai/error.log
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Worker Service

```ini
# /etc/systemd/system/scrapai-worker.service
[Unit]
Description=ScrapAI Background Worker
After=network.target redis.service

[Service]
Type=simple
User=scrapai
Group=scrapai
WorkingDirectory=/opt/scrapai
Environment="PATH=/opt/scrapai/venv/bin"
ExecStart=/opt/scrapai/venv/bin/python -m dramatiq workers.crawl_worker \
    --processes 2 \
    --threads 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Enable Services

```bash
# Create log directory
sudo mkdir -p /var/log/scrapai
sudo chown scrapai:scrapai /var/log/scrapai

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable scrapai-api scrapai-worker
sudo systemctl start scrapai-api scrapai-worker

# Check status
sudo systemctl status scrapai-api
```

## Nginx Reverse Proxy

### Configuration

```nginx
# /etc/nginx/sites-available/scrapai
server {
    listen 80;
    server_name api.example.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;

    # SSL certificates
    ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;

    # SSL settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_req zone=api burst=20 nodelay;

    # Proxy to API
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Health check endpoint (no rate limit)
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        access_log off;
    }
}
```

### Enable Site

```bash
# Create symlink
sudo ln -s /etc/nginx/sites-available/scrapai /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

## Scaling & Load Balancing

### Horizontal Scaling

```yaml
# docker-compose.scale.yml
version: '3.8'

services:
  api:
    deploy:
      replicas: 3
    environment:
      - DATABASE_URL=postgresql://scrapai:password@postgres-lb:5432/scrapai
      - REDIS_HOST=redis

  worker:
    deploy:
      replicas: 2
```

### Load Balancer (HAProxy)

```
# haproxy.cfg
frontend scrapai_front
    bind *:80
    default_backend scrapai_back

backend scrapai_back
    balance roundrobin
    option httpchk GET /health
    server api1 10.0.0.1:8000 check
    server api2 10.0.0.2:8000 check
    server api3 10.0.0.3:8000 check
```

## Monitoring & Logging

### Prometheus Metrics

```python
# Add to api/main.py
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(...)
Instrumentator().instrument(app).expose(app)
```

### Log Rotation

```bash
# /etc/logrotate.d/scrapai
/var/log/scrapai/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 scrapai scrapai
    sharedscripts
    postrotate
        systemctl reload scrapai-api > /dev/null 2>&1 || true
    endscript
}
```

### Health Monitoring

```bash
# Cron job for health checks
*/5 * * * * curl -f http://localhost:8000/health || systemctl restart scrapai-api
```

## Security Hardening

### Checklist

- [ ] Change default SECRET_KEY
- [ ] Use HTTPS (Let's Encrypt)
- [ ] Set up firewall (ufw)
- [ ] Disable root login
- [ ] Use SSH keys only
- [ ] Keep packages updated
- [ ] Set up fail2ban
- [ ] Use environment variables for secrets
- [ ] Regular backups
- [ ] Rate limiting enabled

### Firewall (UFW)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

### Fail2Ban

```ini
# /etc/fail2ban/jail.d/scrapai.conf
[scrapai]
enabled = true
port = http,https
filter = scrapai
logpath = /var/log/scrapai/access.log
maxretry = 10
bantime = 3600
```

## Backup & Recovery

### Database Backup

```bash
# PostgreSQL backup
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql

# Restore
psql $DATABASE_URL < backup_20260309.sql
```

### Automated Backups

```bash
# /etc/cron.daily/scrapai-backup
#!/bin/bash
BACKUP_DIR="/backups/scrapai"
mkdir -p $BACKUP_DIR

# Database
pg_dump $DATABASE_URL | gzip > $BACKUP_DIR/db_$(date +%Y%m%d).sql.gz

# Data directory
tar -czf $BACKUP_DIR/data_$(date +%Y%m%d).tar.gz /opt/scrapai/data

# Keep last 30 days
find $BACKUP_DIR -type f -mtime +30 -delete
```

### Disaster Recovery

```bash
# Full recovery steps
1. Stop services: sudo systemctl stop scrapai-api scrapai-worker
2. Restore database: psql $DATABASE_URL < backup.sql
3. Restore data: tar -xzf data_backup.tar.gz -C /opt/scrapai/
4. Run migrations: alembic upgrade head
5. Start services: sudo systemctl start scrapai-api scrapai-worker
```
