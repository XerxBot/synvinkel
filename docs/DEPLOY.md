# Deploy — Synvinkel

## Stack
- **Backend**: Hetzner CX21 (2 vCPU, 2GB RAM) + Coolify
- **Frontend**: Cloudflare Pages
- **Subdomain**: `synvinkel.analytech.se`

---

## 1. Hetzner + Coolify — backend

### 1.1 Skapa server
1. Skapa konto på [hetzner.com](https://hetzner.com)
2. Skapa projekt → **New Server**
   - Location: **Nuremberg** (EU, GDPR)
   - Image: **Ubuntu 24.04**
   - Type: **CX21** (2 vCPU, 2GB RAM, €5.39/mån)
   - SSH key: lägg till din publik nyckel
3. Notera server-IP (t.ex. `65.21.xxx.xxx`)

### 1.2 DNS
Lägg till A-record i analytech.se DNS:
```
synvinkel.analytech.se  A  65.21.xxx.xxx
```

### 1.3 Installera Coolify
```bash
ssh root@65.21.xxx.xxx
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash
```
Öppna `http://65.21.xxx.xxx:8000` och skapa admin-konto.

### 1.4 Konfigurera deploy i Coolify
1. **New Resource** → **Docker Compose** → **From GitHub**
2. Välj repo `XerxBot/synvinkel`
3. Docker Compose file: `docker-compose.prod.yml`
4. Domain: `synvinkel.analytech.se`
5. Port: `8000`

### 1.5 Miljövariabler i Coolify
```bash
# Generera SECRET_KEY:
openssl rand -hex 32

# Lägg till i Coolify → Environment Variables:
POSTGRES_USER=synvinkel
POSTGRES_PASSWORD=<starkt_lösenord>
REDIS_PASSWORD=<starkt_lösenord>
SECRET_KEY=<genererat_ovan>
ADMIN_EMAIL=xerxes@analytech.se
ALLOWED_ORIGINS=https://synvinkel.analytech.se,https://<cf-pages-subdomain>.pages.dev
```

### 1.6 Första deploy + seed
```bash
# Efter deploy:
docker compose -f docker-compose.prod.yml exec backend python -m app.seed

# Sätt admin-lösenord (registrera via /register och uppgradera):
docker compose -f docker-compose.prod.yml exec db psql -U synvinkel -d synvinkel \
  -c "UPDATE users SET role='admin' WHERE email='xerxes@analytech.se';"
```

### 1.7 note_votes-tabell (befintlig DB)
Om du migrerar från en befintlig dev-DB:
```bash
docker compose exec db psql -U synvinkel -d synvinkel << 'EOF'
CREATE TABLE IF NOT EXISTS note_votes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    note_id     UUID REFERENCES community_notes(id) ON DELETE CASCADE NOT NULL,
    user_id     UUID REFERENCES users(id) NOT NULL,
    is_upvote   BOOLEAN NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(note_id, user_id)
);
EOF
```

---

## 2. Cloudflare Pages — frontend

### 2.1 Förberedelse
```bash
cd frontend
npm install @astrojs/cloudflare
```

### 2.2 Anslut repo i Cloudflare Pages
1. [pages.cloudflare.com](https://pages.cloudflare.com) → **Create project** → **Connect to Git**
2. Välj repo `XerxBot/synvinkel`
3. Build settings:
   - **Framework preset**: None
   - **Build command**: `cd frontend && npm install && npm run build:cf`
   - **Build output directory**: `frontend/dist`
   - **Root directory**: `/`

### 2.3 Miljövariabler i Cloudflare Pages
```
PUBLIC_API_URL = https://synvinkel.analytech.se/api/v1
API_URL        = https://synvinkel.analytech.se/api/v1
```

### 2.4 Custom domain (valfritt)
Lägg till `synvinkel.analytech.se` som custom domain i Cloudflare Pages
**eller** använd den automatiska `*.pages.dev`-URL:en.

---

## 3. Automatisk deploy

Coolify och Cloudflare Pages lyssnar på GitHub-pushar och deployar automatiskt
när `master`-branchen uppdateras.

---

## 4. Backup

```bash
# Schemalägg daglig DB-backup (på servern via cron):
0 3 * * * docker exec synvinkel-db pg_dump -U synvinkel synvinkel | \
  gzip > /backups/synvinkel-$(date +\%Y\%m\%d).sql.gz

# Behåll 30 dagar:
find /backups -name "*.sql.gz" -mtime +30 -delete
```

---

## 5. Monitoring

```bash
# Kolla status:
curl https://synvinkel.analytech.se/health

# Loggar:
docker logs synvinkel-api --tail=100 -f
```
