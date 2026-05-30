#!/bin/bash
set -e
exec > /var/log/auditforge-setup.log 2>&1

# --- System setup ---
apt-get update -y
apt-get install -y ca-certificates curl gnupg nginx git

# --- Docker ---
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable docker
systemctl start docker

# --- Clone repo ---
git clone https://github.com/sabaka3560/auditforge.git /opt/auditforge
cd /opt/auditforge

# --- Environment ---
cat > /opt/auditforge/.env << 'ENVEOF'
DATABASE_URL=postgresql+asyncpg://auditforge:auditforge@db:5432/auditforge
REDIS_URL=redis://redis:6379/0
JWT_SECRET=5c429fa5b76105b13f199322f64dcbdcd70d20601be7b28b04667176fd3c781b
STORAGE_PATH=/app/storage
IDEALS_DIR=ideals
ENVEOF

# --- Start app ---
docker compose up -d

# --- Wait for web to be healthy (up to 3 min) ---
for i in $(seq 1 36); do
  if curl -sf http://localhost:7373/health > /dev/null 2>&1; then
    echo "App healthy after ${i}x5s"
    break
  fi
  sleep 5
done

# --- Nginx reverse proxy ---
cat > /etc/nginx/sites-available/auditforge << 'NGINXEOF'
server {
    listen 80;
    server_name auditforge.tanmaybohra.com _;

    client_max_body_size 55M;

    location / {
        proxy_pass         http://localhost:7373;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
NGINXEOF

ln -sf /etc/nginx/sites-available/auditforge /etc/nginx/sites-enabled/auditforge
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

echo "=== AuditForge setup complete ==="
