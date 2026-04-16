# AIS Data Extractor - Product Requirements Document

## Original Problem Statement
Aplikasi web yang auto mengekstrak data AIS dari akun MarineTraffic, extract per 30 menit: jenis kapal, koordinat, nama kapal, keterangan, history dan data lainnya. Memiliki bot yang mengekstrak seluruh data, merubah menjadi data CSV dan bisa mengirimkan via API ke web lain. Fokus wilayah ASEAN.

## Architecture
- **Backend**: FastAPI + MongoDB (Motor async driver)
- **Frontend**: React + Tailwind CSS + Shadcn UI + react-leaflet
- **Database**: MongoDB (collections: users, vessels, vessel_history, extraction_logs, bot_settings, api_forward_config)
- **Scraper**: MarineTraffic web scraper with simulation data fallback
- **Scheduler**: APScheduler (AsyncIOScheduler) for periodic extraction

## User Personas
- **Maritime Analyst**: Monitors vessel traffic in ASEAN region
- **Data Engineer**: Exports AIS data and sends via API to downstream systems
- **Admin**: Manages bot settings and system configuration

## Core Requirements
- Login authentication (admin account)
- Dashboard with vessel statistics, interactive map, and data tables
- Automated extraction every 30 minutes via bot
- CSV export functionality
- API forwarding to external endpoints
- MarineTraffic web scraping (with simulation fallback)
- ASEAN region bounding box filter (Lat -11 to 25, Lon 95 to 150)

## What's Been Implemented (April 16, 2026)
- [x] JWT-based authentication with admin seed
- [x] Dark theme dashboard with maritime command center aesthetic
- [x] Interactive Leaflet map with CartoDB Dark Matter tiles
- [x] Vessel data table with search, type filter, flag filter, pagination
- [x] CSV export endpoint
- [x] Bot start/stop/extract-now controls
- [x] APScheduler for periodic extraction (configurable interval)
- [x] MarineTraffic scraper class (login + tile-based fetch)
- [x] Simulation data fallback (realistic ASEAN vessel data)
- [x] API forwarding configuration and send
- [x] Extraction logs tracking
- [x] Vessel statistics aggregation

## Data Source Note
- MarineTraffic web scraping is attempted but may fail due to anti-bot protection
- System falls back to **SIMULATED DATA** when real scraping fails
- For production: integrate official MarineTraffic API (~$100/month)

## Prioritized Backlog
### P0 (Critical)
- Integrate official MarineTraffic API for reliable data access
- Verify MarineTraffic scraping actually works with provided credentials

### P1 (Important)
- Historical vessel tracking and route display
- Real-time WebSocket updates
- Port call data integration
- Vessel detail page with full history

### P2 (Nice to have)
- Multi-user support with role-based access
- Email notifications for extraction failures
- Data analytics and vessel movement patterns
- Automated CSV email delivery
- Mobile responsive improvements

## Next Tasks
1. Test MarineTraffic scraping with real credentials in production
2. Add vessel detail page with historical track
3. Implement auto-forward on each extraction
4. Add data retention/cleanup policies
