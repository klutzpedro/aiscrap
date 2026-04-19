# AIS Data Extractor - Product Requirements Document

## Original Problem Statement
Aplikasi web yang auto mengekstrak data AIS dari akun MarineTraffic setiap 30 menit: jenis kapal, koordinat, nama, keterangan, track history. Data dikonversi menjadi CSV dan bisa dikirim via API ke web lain. Fokus awal ASEAN, kemudian diperluas ke Australia, Indian Ocean, dan Red Sea. Fitur terbaru: **Maritime Intelligence & Anomaly Detection** untuk TNI AL di zona strategis (Natuna, Selat Malaka, ALKI I/II/III).

## Architecture
- **Backend**: FastAPI + MongoDB (Motor async)
- **Frontend**: React + Tailwind + Shadcn UI + react-leaflet (Canvas rendering)
- **Scraper**: Playwright + playwright-stealth (bypasses Cloudflare)
- **Scheduler**: APScheduler (AsyncIOScheduler) — 2 jobs: extraction + analytics
- **AI**: emergentintegrations (GPT-4o-mini untuk AI SITREP)

## Collections
- `users`, `vessels`, `vessel_history`, `extraction_logs`, `bot_settings`
- `api_forward_config`, `analytics`, `ai_reports`
- **`analytics_schedule`** (NEW): `{id:"main", enabled, interval_minutes, updated_at}`

## What's Been Implemented
- [x] JWT auth with admin seed (admin / Paparoni83#)
- [x] Playwright stealth extraction (ASEAN + Australia + Indian Ocean + Red Sea, 7000+ vessels)
- [x] Vessel detail page + track history
- [x] APScheduler extraction job (configurable 1-1440 min)
- [x] CSV export + API forward config with photo_url/flag_url
- [x] Leaflet Canvas map (handles 7000+ markers)
- [x] Maritime Intelligence module (`analytics.py`)
  - Zone intrusion, speed anomaly, AIS gap, loitering, position jump
  - Strategic zones: Natuna, Selat Malaka, Papua, ALKI I/II/III
- [x] AI SITREP via emergentintegrations
- [x] **Analytics UI Enhancements (Feb 2026)**
  - Clickable summary cards to filter by severity/type
  - Info modal explaining why each anomaly type is CRITICAL/HIGH
  - Type-filter explanation banner
  - "Track" buttons → vessel track page for each anomaly
  - Customizable analytics schedule UI (30min / 1h / 2h / 6h / 12h / 24h)
- [x] **Analytics Scheduler Backend (Feb 2026)**
  - `GET /api/analytics/schedule` (read current config + next_run)
  - `POST /api/analytics/schedule` (enable/disable + interval 1-10080 min)
  - Auto-restore schedule on backend startup
  - APScheduler `analytics_job` runs `run_full_analysis` periodically

## Key API Endpoints
- Public: `/api/ext/vessels`, `/api/ext/vessels/{id}/track`, `/api/ext/analytics/latest`
- Analytics: `POST /api/ext/analytics/run`, `POST /api/ext/analytics/ai-report`
- **Schedule**: `GET|POST /api/analytics/schedule` (auth required)
- Bot: `GET /api/bot/status`, `POST /api/bot/start|stop|extract-now`

## Next Tasks / Backlog
1. **P1** - "View on Map" link that centers VesselMap on specific anomalous vessel (currently only routes to /track/:shipId)
2. **P1** - Push-notification / webhook when CRITICAL anomaly detected
3. **P2** - Historical analytics trends page (anomalies over time)
4. **P2** - Per-zone bookmark / favorite zones for user
5. **P2** - Refactor server.py (1600+ lines) into routers

## Critical Notes for Agents
- **Scraping**: Playwright intercepts MarineTraffic tiles. DON'T replace with HTTP clients (Cloudflare will block).
- **Map perf**: VesselMap uses `L.canvas()`. DON'T revert to DOM DivIcons (browser crashes at 7000+ markers).
- **VPS workflow**: User self-deploys via GitHub. Remind to Push to GitHub + `git pull && yarn build && supervisorctl restart ais-backend`.
- **LLM**: Uses EMERGENT_LLM_KEY via emergentintegrations.
