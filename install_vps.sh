#!/bin/bash
# ============================================================
#  AIS DATA EXTRACTOR - FULL INSTALLER VIA GITHUB
#  Repo: https://github.com/klutzpedro/aiscrap.git
#  OS: Ubuntu 22.04 | RAM 8GB | 2 Core | Root SSH | HTTP
# ============================================================
#
#  CARA PAKAI:
#    ssh root@IP_VPS_ANDA
#    curl -sL https://raw.githubusercontent.com/klutzpedro/aiscrap/main/install_vps.sh | bash
#
#    ATAU:
#    wget -O install.sh https://raw.githubusercontent.com/klutzpedro/aiscrap/main/install_vps.sh
#    chmod +x install.sh && bash install.sh
#
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

PROJECT_DIR="/opt/ais-extractor"
REPO_URL="https://github.com/klutzpedro/aiscrap.git"
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')

echo -e "${CYAN}${BOLD}"
echo "╔══════════════════════════════════════════════╗"
echo "║   AIS DATA EXTRACTOR - VPS INSTALLER        ║"
echo "║   MarineTraffic Real Data | ASEAN Region     ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  Server IP  : ${GREEN}${SERVER_IP}${NC}"
echo -e "  Repository : ${CYAN}${REPO_URL}${NC}"
echo -e "  Target     : ${CYAN}${PROJECT_DIR}${NC}"
echo ""

# =========================================
# STEP 1: UPDATE SISTEM
# =========================================
echo -e "${CYAN}[1/10] Updating system...${NC}"
export DEBIAN_FRONTEND=noninteractive
apt update -qq && apt upgrade -y -qq
echo -e "${GREEN}  ✓ System updated${NC}"

# =========================================
# STEP 2: INSTALL DEPENDENCIES
# =========================================
echo -e "${CYAN}[2/10] Installing system dependencies...${NC}"
apt install -y -qq \
  curl wget git build-essential software-properties-common \
  python3 python3-pip python3-venv python3-dev \
  nginx supervisor \
  ca-certificates gnupg lsb-release \
  libgconf-2-4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
  libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
  libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
  libnspr4 libnss3 libx11-xcb1 libdrm2 libgtk-3-0 2>/dev/null
echo -e "${GREEN}  ✓ Dependencies installed${NC}"

# =========================================
# STEP 3: INSTALL MONGODB
# =========================================
echo -e "${CYAN}[3/10] Installing MongoDB 7.0...${NC}"
if ! command -v mongod &> /dev/null; then
    curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | \
      gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor 2>/dev/null
    echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | \
      tee /etc/apt/sources.list.d/mongodb-org-7.0.list > /dev/null
    apt update -qq && apt install -y -qq mongodb-org
fi
systemctl start mongod 2>/dev/null
systemctl enable mongod 2>/dev/null
echo -e "${GREEN}  ✓ MongoDB running${NC}"

# =========================================
# STEP 4: INSTALL NODE.JS & YARN
# =========================================
echo -e "${CYAN}[4/10] Installing Node.js 20 & Yarn...${NC}"
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - > /dev/null 2>&1
    apt install -y -qq nodejs
fi
npm install -g yarn 2>/dev/null
echo -e "${GREEN}  ✓ Node.js $(node -v) | Yarn $(yarn -v)${NC}"

# =========================================
# STEP 5: CLONE REPOSITORY
# =========================================
echo -e "${CYAN}[5/10] Cloning repository...${NC}"
if [ -d "${PROJECT_DIR}" ]; then
    echo -e "${YELLOW}  Project dir exists, pulling latest...${NC}"
    cd ${PROJECT_DIR} && git pull origin main 2>/dev/null || true
else
    git clone ${REPO_URL} ${PROJECT_DIR}
fi
echo -e "${GREEN}  ✓ Repository cloned to ${PROJECT_DIR}${NC}"

# =========================================
# STEP 6: SETUP PYTHON BACKEND
# =========================================
echo -e "${CYAN}[6/10] Setting up Python backend...${NC}"
cd ${PROJECT_DIR}/backend

# Buat virtual environment
python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip -q
pip install -q \
  fastapi==0.110.1 uvicorn==0.25.0 "python-dotenv>=1.0.1" \
  motor==3.3.1 pymongo==4.5.0 "pydantic>=2.6.4" \
  bcrypt==4.1.3 "pyjwt>=2.10.1" "requests>=2.31.0" \
  "apscheduler>=3.11.0" "beautifulsoup4>=4.12.0" "lxml>=5.0.0" \
  "cloudscraper>=1.2.71" "playwright>=1.40.0" "playwright-stealth>=2.0.0"

echo -e "${GREEN}  ✓ Python packages installed${NC}"

# =========================================
# STEP 7: INSTALL PLAYWRIGHT CHROMIUM
# =========================================
echo -e "${CYAN}[7/10] Installing Playwright Chromium (untuk scraping MarineTraffic)...${NC}"
playwright install chromium 2>/dev/null
playwright install-deps chromium 2>/dev/null || true
echo -e "${GREEN}  ✓ Playwright Chromium installed${NC}"

# =========================================
# STEP 8: CREATE .ENV FILES
# =========================================
echo -e "${CYAN}[8/10] Creating configuration files...${NC}"

# Generate JWT secret
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# Backend .env - PENTING: pakai 'EOF' (quoted) agar # tidak ter-strip
cat > ${PROJECT_DIR}/backend/.env << 'ENVEOF'
MONGO_URL="mongodb://localhost:27017"
DB_NAME="ais_extractor"
CORS_ORIGINS="*"
JWT_SECRET="PLACEHOLDER_JWT"
ADMIN_EMAIL="admin"
ADMIN_PASSWORD="Paparoni83#"
MT_EMAIL="nedwijayanto@gmail.com"
MT_PASSWORD="Paparoni83"
ENVEOF

# Inject JWT secret (karena heredoc quoted, variable tidak di-expand)
sed -i "s|PLACEHOLDER_JWT|${JWT_SECRET}|" ${PROJECT_DIR}/backend/.env

# Verifikasi .env benar
echo "  Verifikasi .env:"
grep ADMIN_PASSWORD ${PROJECT_DIR}/backend/.env

# Frontend .env
cat > ${PROJECT_DIR}/frontend/.env << ENVEOF
REACT_APP_BACKEND_URL=http://${SERVER_IP}
ENVEOF

echo -e "${GREEN}  ✓ Backend .env created${NC}"
echo -e "${GREEN}  ✓ Frontend .env → http://${SERVER_IP}${NC}"

# =========================================
# STEP 9: BUILD FRONTEND
# =========================================
echo -e "${CYAN}[9/10] Building frontend (React)...${NC}"
cd ${PROJECT_DIR}/frontend
yarn install --network-timeout 120000 2>/dev/null
yarn build 2>/dev/null
echo -e "${GREEN}  ✓ Frontend built${NC}"

# =========================================
# STEP 10: CONFIGURE NGINX + SUPERVISOR
# =========================================
echo -e "${CYAN}[10/10] Configuring Nginx & Supervisor...${NC}"

# Nginx
cat > /etc/nginx/sites-available/ais-extractor << 'NGINXEOF'
server {
    listen 80;
    server_name _;

    root /opt/ais-extractor/frontend/build;
    index index.html;

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
    gzip_min_length 256;
    client_max_body_size 50M;

    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
    }

    # React SPA
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
NGINXEOF

ln -sf /etc/nginx/sites-available/ais-extractor /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t > /dev/null 2>&1
systemctl restart nginx
systemctl enable nginx 2>/dev/null

# Supervisor
cat > /etc/supervisor/conf.d/ais-backend.conf << 'SUPEOF'
[program:ais-backend]
command=/opt/ais-extractor/backend/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001 --workers 1
directory=/opt/ais-extractor/backend
user=root
autostart=true
autorestart=true
stderr_logfile=/var/log/ais-backend.err.log
stdout_logfile=/var/log/ais-backend.out.log
stderr_logfile_maxbytes=10MB
stdout_logfile_maxbytes=10MB
environment=PATH="/opt/ais-extractor/backend/venv/bin:%(ENV_PATH)s"
stopwaitsecs=30
SUPEOF

supervisorctl reread > /dev/null 2>&1
supervisorctl update > /dev/null 2>&1
supervisorctl restart ais-backend 2>/dev/null || supervisorctl start ais-backend 2>/dev/null

# Firewall
ufw allow 22/tcp > /dev/null 2>&1
ufw allow 80/tcp > /dev/null 2>&1
ufw --force enable > /dev/null 2>&1

echo -e "${GREEN}  ✓ Nginx, Supervisor & Firewall configured${NC}"

# =========================================
# VERIFIKASI
# =========================================
echo ""
sleep 3

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  VERIFIKASI INSTALASI${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# MongoDB
if systemctl is-active --quiet mongod; then
    echo -e "  MongoDB    : ${GREEN}Running${NC}"
else
    echo -e "  MongoDB    : ${RED}NOT Running${NC}"
fi

# Nginx
if systemctl is-active --quiet nginx; then
    echo -e "  Nginx      : ${GREEN}Running${NC}"
else
    echo -e "  Nginx      : ${RED}NOT Running${NC}"
fi

# Backend
BACKEND_STATUS=$(supervisorctl status ais-backend 2>/dev/null | awk '{print $2}')
if [ "$BACKEND_STATUS" = "RUNNING" ]; then
    echo -e "  Backend    : ${GREEN}Running${NC}"
else
    echo -e "  Backend    : ${RED}${BACKEND_STATUS:-NOT Running}${NC}"
fi

# API Test
API_RESPONSE=$(curl -s http://localhost:8001/api/ 2>/dev/null)
if echo "$API_RESPONSE" | grep -q "AIS Data Extractor"; then
    echo -e "  API        : ${GREEN}OK${NC}"
else
    echo -e "  API        : ${RED}NOT responding${NC}"
fi

echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║        INSTALASI BERHASIL!                   ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}Akses:${NC}    ${GREEN}http://${SERVER_IP}${NC}"
echo -e "  ${BOLD}Login:${NC}    ${GREEN}admin${NC} / ${GREEN}Paparoni83#${NC}"
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${BOLD}Perintah berguna:${NC}"
echo -e "  Log backend  : ${CYAN}tail -f /var/log/ais-backend.err.log${NC}"
echo -e "  Restart      : ${CYAN}supervisorctl restart ais-backend${NC}"
echo -e "  Status       : ${CYAN}supervisorctl status ais-backend${NC}"
echo -e "  Update code  : ${CYAN}cd /opt/ais-extractor && git pull && supervisorctl restart ais-backend${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
