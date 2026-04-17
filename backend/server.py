from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Query
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import math
import time
import io
import csv
import json
import asyncio
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
import bcrypt
import jwt
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ===== CONFIG =====
mongo_url = os.environ['MONGO_URL']
db_name = os.environ['DB_NAME']
async_client = AsyncIOMotorClient(mongo_url)
db = async_client[db_name]

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALGORITHM = "HS256"
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
MT_EMAIL = os.environ.get('MT_EMAIL', '')
MT_PASSWORD = os.environ.get('MT_PASSWORD', '')

ASEAN_BBOX = {"min_lat": -11.0, "max_lat": 25.0, "min_lon": 95.0, "max_lon": 150.0}

# ASEAN tile coordinates at zoom 5
ASEAN_TILES_Z5 = [
    (24, 14), (24, 15), (24, 16), (24, 17),
    (25, 14), (25, 15), (25, 16), (25, 17),
    (26, 14), (26, 15), (26, 16), (26, 17),
    (27, 14), (27, 15), (27, 16), (27, 17),
]

SHIP_TYPE_MAP = {
    "1": "Reserved", "2": "Reserved", "3": "Special Craft", "4": "High Speed Craft",
    "5": "Special Craft", "6": "Passenger", "7": "Cargo", "8": "Tanker", "9": "Other",
}
GT_SHIP_TYPE_MAP = {
    "1": "Reserved", "2": "Wing in Ground", "3": "Vessel", "4": "HSC",
    "5": "Special Craft", "6": "Passenger", "7": "Cargo - Hazardous A",
    "8": "Cargo", "9": "Cargo - Hazardous B", "10": "Cargo - Hazardous C",
    "11": "Cargo - Hazardous D", "12": "Tanker - Hazardous A",
    "13": "Tanker", "14": "Tanker - Hazardous B", "15": "Tanker - Hazardous C",
    "16": "Tanker - Hazardous D", "17": "Tanker", "18": "Other",
    "19": "Passenger", "20": "Container Ship", "21": "Bulk Carrier",
    "22": "General Cargo", "23": "Ro-Ro Cargo", "24": "Reefer",
    "25": "Vehicle Carrier", "26": "LNG Carrier", "27": "LPG Carrier",
    "28": "Crude Oil Tanker", "29": "Chemical Tanker", "30": "Product Tanker",
    "31": "Oil/Chemical Tanker", "32": "Offshore Supply", "33": "Tug",
    "34": "Pleasure Craft", "35": "Sailing Vessel", "36": "Fishing",
    "37": "Military", "38": "Research Vessel", "39": "Dredger",
    "40": "Yacht", "50": "Pilot Vessel", "51": "SAR", "52": "Tug",
    "53": "Port Tender", "54": "Anti-Pollution", "55": "Law Enforcement",
    "56": "FPSO/FSO",
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
api_router = APIRouter(prefix="/api")
scheduler = AsyncIOScheduler()

# ===== AUTH HELPERS =====
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

def create_access_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email, "exp": datetime.now(timezone.utc) + timedelta(hours=24), "type": "access"}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ===== PYDANTIC MODELS =====
class LoginRequest(BaseModel):
    email: str
    password: str

class ForwardConfig(BaseModel):
    endpoint_url: str
    method: str = "POST"
    headers: Optional[dict] = None
    enabled: bool = True

# ===== MARINETRAFFIC PLAYWRIGHT SCRAPER =====
async def scrape_marinetraffic_real():
    """Use Playwright to scrape real vessel data from MarineTraffic"""
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    logger.info("Starting real MarineTraffic scrape with Playwright...")
    vessels = []
    seen_ids = set()

    try:
        stealth = Stealth()
        async with async_playwright() as p:
            stealth.hook_playwright_context(p)
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
            page = await context.new_page()

            raw_responses = []

            async def capture_response(response):
                url = response.url
                if 'getData/get_data_json' in url:
                    try:
                        body = await response.text()
                        if body and not body.startswith('<!DOCTYPE'):
                            raw_responses.append(body)
                    except Exception:
                        pass

            page.on('response', capture_response)

            # Step 1: Login to MarineTraffic
            logger.info("Navigating to MarineTraffic login...")
            await page.goto('https://www.marinetraffic.com/en/users/login', timeout=30000)
            await page.wait_for_timeout(5000)

            title = await page.title()
            if 'Cloudflare' not in title and 'Attention' not in title:
                # Fill login - Auth0 style (email first, then password)
                try:
                    visible_inputs = page.locator('input:visible')
                    cnt = await visible_inputs.count()

                    if cnt == 1:
                        # Email-first flow
                        await visible_inputs.first.fill(MT_EMAIL)
                        submit = page.locator('button[type="submit"]:visible, button:has-text("Continue"):visible')
                        if await submit.count() > 0:
                            await submit.first.click()
                            await page.wait_for_timeout(3000)

                        pwd = page.locator('input[type="password"]:visible')
                        if await pwd.count() > 0:
                            await pwd.first.fill(MT_PASSWORD)
                            submit2 = page.locator('button[type="submit"]:visible, button:has-text("Continue"):visible, button:has-text("Log in"):visible')
                            if await submit2.count() > 0:
                                await submit2.first.click()
                                await page.wait_for_timeout(5000)

                    elif cnt >= 2:
                        await visible_inputs.nth(0).fill(MT_EMAIL)
                        await visible_inputs.nth(1).fill(MT_PASSWORD)
                        submit = page.locator('button[type="submit"]:visible')
                        if await submit.count() > 0:
                            await submit.first.click()
                            await page.wait_for_timeout(5000)

                    logger.info(f"After login, URL: {page.url}")
                except Exception as e:
                    logger.warning(f"Login form error: {e}")

            # Step 2: Navigate to ASEAN map and capture vessel data
            logger.info("Navigating to ASEAN map view...")
            await page.goto(
                'https://www.marinetraffic.com/en/ais/home/centerx:115/centery:5/zoom:5',
                timeout=30000
            )
            await page.wait_for_timeout(15000)

            logger.info(f"Captured {len(raw_responses)} tile responses")

            # Step 3: Parse all captured responses
            for raw in raw_responses:
                try:
                    data = json.loads(raw)
                    rows = []
                    if isinstance(data, dict):
                        rows = data.get('data', {}).get('rows', [])
                    elif isinstance(data, list):
                        rows = data

                    for row in rows:
                        try:
                            lat = float(row.get('LAT', 0))
                            lon = float(row.get('LON', 0))
                            if lat == 0 and lon == 0:
                                continue
                            # Filter ASEAN bounding box
                            if not (ASEAN_BBOX['min_lat'] <= lat <= ASEAN_BBOX['max_lat'] and
                                    ASEAN_BBOX['min_lon'] <= lon <= ASEAN_BBOX['max_lon']):
                                continue

                            ship_id = row.get('SHIP_ID', '')
                            if ship_id in seen_ids:
                                continue
                            seen_ids.add(ship_id)

                            shiptype = str(row.get('SHIPTYPE', ''))
                            gt_shiptype = str(row.get('GT_SHIPTYPE', ''))
                            type_name = row.get('TYPE_NAME', '')

                            if type_name:
                                vessel_type = type_name
                            elif gt_shiptype and gt_shiptype in GT_SHIP_TYPE_MAP:
                                vessel_type = GT_SHIP_TYPE_MAP[gt_shiptype]
                            elif shiptype and shiptype in SHIP_TYPE_MAP:
                                vessel_type = SHIP_TYPE_MAP[shiptype]
                            else:
                                vessel_type = f"Type {shiptype}" if shiptype else "Unknown"

                            speed_raw = row.get('SPEED', '0')
                            try:
                                speed = round(float(speed_raw) / 10.0, 1)
                            except (ValueError, TypeError):
                                speed = 0.0

                            course_raw = row.get('COURSE')
                            try:
                                course = round(float(course_raw), 1) if course_raw else None
                            except (ValueError, TypeError):
                                course = None

                            heading_raw = row.get('HEADING')
                            try:
                                heading = round(float(heading_raw), 1) if heading_raw else None
                            except (ValueError, TypeError):
                                heading = None

                            status_name = row.get('STATUS_NAME', '')
                            status_code = row.get('STATUS', '')
                            if status_name:
                                nav_status = status_name
                            elif status_code:
                                status_map = {"0": "Under way using engine", "1": "At anchor", "2": "Not under command",
                                              "3": "Restricted maneuverability", "4": "Constrained by draught",
                                              "5": "Moored", "8": "Under way sailing"}
                                nav_status = status_map.get(str(status_code), f"Status {status_code}")
                            else:
                                nav_status = "N/A"

                            vessel = {
                                "ship_id": ship_id,
                                "mmsi": str(row.get('MMSI', ship_id)),
                                "imo": str(row.get('IMO', '')) if row.get('IMO') else None,
                                "name": row.get('SHIPNAME', 'Unknown'),
                                "vessel_type": vessel_type,
                                "flag": row.get('FLAG', ''),
                                "latitude": lat,
                                "longitude": lon,
                                "speed": speed,
                                "course": course,
                                "heading": heading,
                                "nav_status": nav_status,
                                "destination": row.get('DESTINATION', ''),
                                "eta": row.get('ETA', ''),
                                "length": row.get('LENGTH', ''),
                                "width": row.get('WIDTH', ''),
                                "dwt": row.get('DWT', ''),
                                "elapsed_min": row.get('ELAPSED', ''),
                            }
                            vessels.append(vessel)
                        except Exception:
                            continue
                except Exception as e:
                    logger.warning(f"Parse error: {e}")
                    continue

            await browser.close()

    except Exception as e:
        logger.error(f"Playwright scrape error: {e}")

    logger.info(f"Scraped {len(vessels)} vessels in ASEAN region from MarineTraffic (REAL DATA)")
    return vessels


# ===== AUTO FORWARD =====
async def auto_forward_data(vessels_data):
    """Otomatis kirim data ke endpoint yang dikonfigurasi setelah extraction"""
    try:
        config = await db.api_forward_config.find_one({"id": "main"}, {"_id": 0})
        if not config or not config.get("enabled") or not config.get("endpoint_url"):
            return

        logger.info(f"Auto-forwarding {len(vessels_data)} vessels to {config['endpoint_url']}...")

        # Bersihkan _id dari vessels
        clean_vessels = []
        for v in vessels_data:
            cv = {k: v for k, v in v.items() if k != '_id'}
            clean_vessels.append(cv)

        headers = config.get("headers") or {}
        headers["Content-Type"] = "application/json"
        method = config.get("method", "POST").upper()

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "ais_extractor_marinetraffic",
            "region": "ASEAN",
            "vessel_count": len(clean_vessels),
            "vessels": clean_vessels,
        }

        if method == "POST":
            resp = requests.post(config["endpoint_url"], json=payload, headers=headers, timeout=30)
        elif method == "PUT":
            resp = requests.put(config["endpoint_url"], json=payload, headers=headers, timeout=30)
        else:
            logger.warning(f"Unsupported forward method: {method}")
            return

        # Log hasil forward
        await db.forward_logs.insert_one({
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoint": config["endpoint_url"],
            "status_code": resp.status_code,
            "vessels_sent": len(clean_vessels),
            "success": 200 <= resp.status_code < 300,
        })

        logger.info(f"Auto-forward complete: {len(clean_vessels)} vessels → {config['endpoint_url']} (status {resp.status_code})")

    except Exception as e:
        logger.error(f"Auto-forward failed: {e}")
        await db.forward_logs.insert_one({
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoint": config.get("endpoint_url", "unknown") if config else "unknown",
            "status_code": 0,
            "vessels_sent": 0,
            "success": False,
            "error": str(e),
        })


# ===== SCRAPER STATE =====
bot_running = False

# ===== EXTRACTION LOGIC =====
async def run_extraction():
    start_time = time.time()
    log_id = str(uuid.uuid4())
    source = "marinetraffic"
    error_msg = None
    vessels_data = None

    try:
        logger.info("Starting extraction from MarineTraffic (real data)...")
        vessels_data = await scrape_marinetraffic_real()

        if not vessels_data or len(vessels_data) == 0:
            raise Exception("No vessel data retrieved from MarineTraffic. Check credentials or connectivity.")

        now = datetime.now(timezone.utc).isoformat()
        for v in vessels_data:
            v["id"] = str(uuid.uuid4())
            v["last_updated"] = now
            v["source"] = source
            v["extraction_id"] = log_id

        await db.vessels.delete_many({})
        if vessels_data:
            await db.vessels.insert_many(vessels_data)

        for v in vessels_data:
            history_doc = {**v, "recorded_at": now}
            history_doc.pop("_id", None)
            await db.vessel_history.insert_one(history_doc)

        duration = round(time.time() - start_time, 2)
        log_entry = {
            "id": log_id,
            "timestamp": now,
            "status": "success",
            "source": source,
            "vessels_count": len(vessels_data),
            "duration_seconds": duration,
            "error_message": None,
        }
        await db.extraction_logs.insert_one(log_entry)
        logger.info(f"Extraction complete: {len(vessels_data)} REAL vessels in {duration}s")

        # AUTO FORWARD setelah extraction berhasil
        await auto_forward_data(vessels_data)

    except Exception as e:
        duration = round(time.time() - start_time, 2)
        error_msg = str(e)
        logger.error(f"Extraction failed: {error_msg}")
        log_entry = {
            "id": log_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "failed",
            "source": source,
            "vessels_count": 0,
            "duration_seconds": duration,
            "error_message": error_msg,
        }
        await db.extraction_logs.insert_one(log_entry)


# ===== AUTH ROUTES =====
@api_router.post("/auth/login")
async def login(req: LoginRequest):
    user = await db.users.find_one({"email": req.email}, {"_id": 0})
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user["id"], user["email"])
    return {
        "token": token,
        "user": {"id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"]}
    }

@api_router.get("/auth/me")
async def get_me(user=Depends(get_current_user)):
    return user

@api_router.post("/auth/logout")
async def logout():
    return {"message": "Logged out"}

@api_router.post("/auth/reset-admin")
async def reset_admin():
    """Reset admin password dari .env - untuk troubleshooting"""
    admin_email = ADMIN_EMAIL
    admin_password = ADMIN_PASSWORD
    existing = await db.users.find_one({"email": admin_email}, {"_id": 0})
    if existing:
        new_hash = hash_password(admin_password)
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": new_hash}})
        return {"message": f"Admin password reset for '{admin_email}'"}
    else:
        admin_id = str(uuid.uuid4())
        await db.users.insert_one({
            "id": admin_id, "email": admin_email, "password_hash": hash_password(admin_password),
            "name": "Administrator", "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        return {"message": f"Admin user created: '{admin_email}'"}


# ===== VESSEL ROUTES =====
@api_router.get("/vessels")
async def get_vessels(
    search: Optional[str] = None,
    vessel_type: Optional[str] = None,
    flag: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    user=Depends(get_current_user)
):
    query = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"mmsi": {"$regex": search, "$options": "i"}},
            {"imo": {"$regex": search, "$options": "i"}},
        ]
    if vessel_type:
        query["vessel_type"] = vessel_type
    if flag:
        query["flag"] = flag

    total = await db.vessels.count_documents(query)
    skip = (page - 1) * limit
    vessels = await db.vessels.find(query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    return {"vessels": vessels, "total": total, "page": page, "limit": limit, "pages": math.ceil(total / limit) if total > 0 else 0}

@api_router.get("/vessels/stats")
async def get_vessel_stats(user=Depends(get_current_user)):
    total = await db.vessels.count_documents({})
    type_pipeline = [{"$group": {"_id": "$vessel_type", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
    type_stats = await db.vessels.aggregate(type_pipeline).to_list(50)
    flag_pipeline = [{"$group": {"_id": "$flag", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}, {"$limit": 10}]
    flag_stats = await db.vessels.aggregate(flag_pipeline).to_list(10)
    speed_pipeline = [{"$group": {"_id": None, "avg_speed": {"$avg": "$speed"}, "max_speed": {"$max": "$speed"}}}]
    speed_stats = await db.vessels.aggregate(speed_pipeline).to_list(1)

    last_log = await db.extraction_logs.find_one({}, {"_id": 0}, sort=[("timestamp", -1)])
    total_extractions = await db.extraction_logs.count_documents({})

    return {
        "total_vessels": total,
        "vessel_types": [{"type": t["_id"] or "Unknown", "count": t["count"]} for t in type_stats],
        "top_flags": [{"flag": f["_id"] or "N/A", "count": f["count"]} for f in flag_stats],
        "avg_speed": round(speed_stats[0]["avg_speed"], 1) if speed_stats and speed_stats[0].get("avg_speed") else 0,
        "max_speed": round(speed_stats[0]["max_speed"], 1) if speed_stats and speed_stats[0].get("max_speed") else 0,
        "last_extraction": last_log,
        "total_extractions": total_extractions,
    }

@api_router.get("/vessels/types")
async def get_vessel_types(user=Depends(get_current_user)):
    types = await db.vessels.distinct("vessel_type")
    return {"types": sorted([t for t in types if t])}

@api_router.get("/vessels/flags")
async def get_vessel_flags(user=Depends(get_current_user)):
    flags = await db.vessels.distinct("flag")
    return {"flags": sorted([f for f in flags if f])}

@api_router.get("/vessels/export/csv")
async def export_vessels_csv(user=Depends(get_current_user)):
    vessels = await db.vessels.find({}, {"_id": 0}).to_list(10000)
    if not vessels:
        raise HTTPException(status_code=404, detail="No vessel data to export")

    output = io.StringIO()
    fieldnames = ["name", "mmsi", "imo", "vessel_type", "flag", "latitude", "longitude",
                  "speed", "course", "heading", "nav_status", "destination", "eta",
                  "length", "width", "dwt", "last_updated", "source"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    for v in vessels:
        writer.writerow(v)

    output.seek(0)
    filename = f"ais_data_asean_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@api_router.get("/vessels/map")
async def get_vessels_for_map(user=Depends(get_current_user)):
    vessels = await db.vessels.find(
        {}, {"_id": 0, "name": 1, "mmsi": 1, "vessel_type": 1, "latitude": 1,
             "longitude": 1, "speed": 1, "course": 1, "flag": 1, "nav_status": 1,
             "destination": 1, "length": 1, "dwt": 1}
    ).to_list(10000)
    return {"vessels": vessels}


# ===== BOT ROUTES =====
@api_router.get("/bot/status")
async def get_bot_status(user=Depends(get_current_user)):
    global bot_running
    last_log = await db.extraction_logs.find_one({}, {"_id": 0}, sort=[("timestamp", -1)])
    total = await db.extraction_logs.count_documents({})
    settings = await db.bot_settings.find_one({"id": "main"}, {"_id": 0})
    interval = settings.get("interval_minutes", 30) if settings else 30

    next_run = None
    jobs = scheduler.get_jobs()
    if jobs:
        next_run = jobs[0].next_run_time.isoformat() if jobs[0].next_run_time else None

    return {
        "running": bot_running,
        "interval_minutes": interval,
        "last_extraction": last_log.get("timestamp") if last_log else None,
        "next_extraction": next_run,
        "total_extractions": total,
        "mt_connected": True,
        "data_source": "MarineTraffic (Real Data)",
    }

@api_router.post("/bot/start")
async def start_bot(user=Depends(get_current_user)):
    global bot_running
    settings = await db.bot_settings.find_one({"id": "main"}, {"_id": 0})
    interval = settings.get("interval_minutes", 30) if settings else 30

    if not bot_running:
        scheduler.add_job(run_extraction, 'interval', minutes=interval, id='extraction_job', replace_existing=True)
        if not scheduler.running:
            scheduler.start()
        bot_running = True
    return {"message": "Bot started", "running": True, "interval_minutes": interval}

@api_router.post("/bot/stop")
async def stop_bot(user=Depends(get_current_user)):
    global bot_running
    try:
        scheduler.remove_job('extraction_job')
    except Exception:
        pass
    bot_running = False
    return {"message": "Bot stopped", "running": False}

@api_router.post("/bot/extract-now")
async def extract_now(user=Depends(get_current_user)):
    await run_extraction()
    return {"message": "Extraction completed"}

@api_router.post("/bot/settings")
async def update_bot_settings(interval_minutes: int = Query(30, ge=1, le=1440), user=Depends(get_current_user)):
    global bot_running
    await db.bot_settings.update_one(
        {"id": "main"},
        {"$set": {"id": "main", "interval_minutes": interval_minutes}},
        upsert=True
    )
    if bot_running:
        try:
            scheduler.remove_job('extraction_job')
        except Exception:
            pass
        scheduler.add_job(run_extraction, 'interval', minutes=interval_minutes, id='extraction_job', replace_existing=True)
    return {"message": f"Interval updated to {interval_minutes} minutes", "interval_minutes": interval_minutes}

@api_router.get("/bot/logs")
async def get_extraction_logs(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), user=Depends(get_current_user)):
    total = await db.extraction_logs.count_documents({})
    skip = (page - 1) * limit
    logs = await db.extraction_logs.find({}, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)
    return {"logs": logs, "total": total, "page": page, "pages": math.ceil(total / limit) if total > 0 else 0}


# ===== FORWARD ROUTES =====
@api_router.get("/forward/config")
async def get_forward_config(user=Depends(get_current_user)):
    config = await db.api_forward_config.find_one({"id": "main"}, {"_id": 0})
    return config or {"id": "main", "endpoint_url": "", "method": "POST", "headers": {}, "enabled": False}

@api_router.post("/forward/config")
async def update_forward_config(config: ForwardConfig, user=Depends(get_current_user)):
    doc = config.model_dump()
    doc["id"] = "main"
    await db.api_forward_config.update_one({"id": "main"}, {"$set": doc}, upsert=True)
    return {"message": "Config updated", **doc}

@api_router.post("/forward/send")
async def send_data_to_api(user=Depends(get_current_user)):
    config = await db.api_forward_config.find_one({"id": "main"}, {"_id": 0})
    if not config or not config.get("endpoint_url"):
        raise HTTPException(status_code=400, detail="No forwarding endpoint configured")

    vessels = await db.vessels.find({}, {"_id": 0}).to_list(10000)
    if not vessels:
        raise HTTPException(status_code=404, detail="No vessel data to send")

    try:
        headers = config.get("headers") or {}
        headers["Content-Type"] = "application/json"
        method = config.get("method", "POST").upper()
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "ais_extractor_marinetraffic",
            "region": "ASEAN",
            "vessel_count": len(vessels),
            "vessels": vessels,
        }
        if method == "POST":
            resp = requests.post(config["endpoint_url"], json=payload, headers=headers, timeout=30)
        elif method == "PUT":
            resp = requests.put(config["endpoint_url"], json=payload, headers=headers, timeout=30)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported method: {method}")
        return {"message": "Data sent successfully", "status_code": resp.status_code, "vessels_sent": len(vessels)}
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Failed to send data: {str(e)}")

@api_router.get("/forward/logs")
async def get_forward_logs(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), user=Depends(get_current_user)):
    total = await db.forward_logs.count_documents({})
    skip = (page - 1) * limit
    logs = await db.forward_logs.find({}, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)
    return {"logs": logs, "total": total, "page": page, "pages": math.ceil(total / limit) if total > 0 else 0}


# ===== HEALTH =====
@api_router.get("/")
async def root():
    return {"message": "AIS Data Extractor API - MarineTraffic Real Data", "version": "2.0.0", "region": "ASEAN", "source": "MarineTraffic"}


# ===== STARTUP =====
async def seed_admin():
    existing = await db.users.find_one({"email": ADMIN_EMAIL}, {"_id": 0})
    if existing is None:
        admin_id = str(uuid.uuid4())
        hashed = hash_password(ADMIN_PASSWORD)
        await db.users.insert_one({
            "id": admin_id, "email": ADMIN_EMAIL, "password_hash": hashed,
            "name": "Administrator", "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        logger.info(f"Admin user created: {ADMIN_EMAIL}")
    elif not verify_password(ADMIN_PASSWORD, existing["password_hash"]):
        await db.users.update_one({"email": ADMIN_EMAIL}, {"$set": {"password_hash": hash_password(ADMIN_PASSWORD)}})

    try:
        cred_path = Path(__file__).parent.parent / "memory" / "test_credentials.md"
        cred_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cred_path, "w") as f:
            f.write(f"# Test Credentials\n\n## Admin\n- Email: {ADMIN_EMAIL}\n- Password: {ADMIN_PASSWORD}\n- Role: admin\n\n## Auth Endpoints\n- POST /api/auth/login\n- GET /api/auth/me\n- POST /api/auth/logout\n")
    except Exception:
        pass

@app.on_event("startup")
async def startup():
    await seed_admin()
    await db.users.create_index("email", unique=True)
    await db.vessels.create_index("mmsi")
    await db.vessels.create_index("ship_id")
    await db.extraction_logs.create_index("timestamp")
    logger.info("AIS Data Extractor v2 started - MarineTraffic Real Data Source")

@app.on_event("shutdown")
async def shutdown():
    if scheduler.running:
        scheduler.shutdown()
    async_client.close()

app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
