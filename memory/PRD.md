# AIS Data Extractor - Product Requirements Document

## Original Problem Statement
Aplikasi web yang auto mengekstrak data AIS dari akun MarineTraffic, extract per 30 menit: jenis kapal, koordinat, nama kapal, keterangan, history dan data lainnya. Memiliki bot yang mengekstrak seluruh data, merubah menjadi data CSV dan bisa mengirimkan via API ke web lain. Fokus wilayah ASEAN.

## Architecture
- **Backend**: FastAPI + MongoDB (Motor async driver)
- **Frontend**: React + Tailwind CSS + Shadcn UI + react-leaflet
- **Database**: MongoDB (collections: users, vessels, vessel_history, extraction_logs, bot_settings, api_forward_config)
- **Scraper**: Playwright + playwright-stealth (bypasses Cloudflare, real MarineTraffic data)
- **Scheduler**: APScheduler (AsyncIOScheduler) for periodic extraction every 30 min

## Data Source
- **REAL DATA** from MarineTraffic via Playwright browser scraping
- Account: nedwijayanto@gmail.com
- Auth0/Kpler login flow handled automatically
- getData/get_data_json_4 tile endpoints captured via network interception
- ~5000+ vessels per extraction in ASEAN region
- Extraction time: ~30 seconds per run

## What's Been Implemented (April 16, 2026)
- [x] JWT auth with admin seed
- [x] Dark theme command center dashboard (Chivo + IBM Plex Sans fonts)
- [x] Leaflet map with CartoDB Dark Matter tiles showing 5000+ vessels
- [x] REAL MarineTraffic data extraction via Playwright stealth browser
- [x] APScheduler bot (configurable interval, default 30 min)
- [x] CSV export
- [x] API forwarding to external endpoints
- [x] Extraction logs with real timestamps and stats
- [x] Vessel search, type filter, flag filter, pagination

## Next Tasks
1. Add vessel detail page with historical track
2. Implement auto-forward on each extraction
3. Add WebSocket for real-time updates
4. Improve vessel type mapping for better categorization
