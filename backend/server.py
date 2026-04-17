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

ASEAN_BBOX = {"min_lat": -47.0, "max_lat": 32.0, "min_lon": 32.0, "max_lon": 180.0}

# Coverage: ASEAN + Australia/NZ + Samudra Hindia/Sri Lanka + Laut Merah/Teluk Arab
COVERAGE_LABEL = "ASEAN + Australia + Indian Ocean + Red Sea"

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
            try:
                await page.goto('https://www.marinetraffic.com/en/users/login', timeout=45000)
            except Exception as nav_err:
                logger.warning(f"Login page navigation error: {nav_err}")
                await browser.close()
                return vessels

            await page.wait_for_timeout(6000)

            title = await page.title()
            logger.info(f"Login page title: {title}")

            # Jika Cloudflare challenge, tunggu lebih lama
            if 'Cloudflare' in title or 'Attention' in title or 'challenge' in title.lower():
                logger.info("Cloudflare challenge detected, waiting 15s...")
                await page.wait_for_timeout(15000)
                title = await page.title()
                if 'Cloudflare' in title:
                    logger.error("Still blocked by Cloudflare after waiting")
                    await browser.close()
                    return vessels

            # Fill login - Auth0 style (email first, then password)
            try:
                visible_inputs = page.locator('input:visible')
                cnt = await visible_inputs.count()
                logger.info(f"Found {cnt} visible inputs on login page")

                if cnt == 1:
                    await visible_inputs.first.fill(MT_EMAIL)
                    submit = page.locator('button[type="submit"]:visible, button:has-text("Continue"):visible')
                    if await submit.count() > 0:
                        await submit.first.click()
                        await page.wait_for_timeout(4000)

                    pwd = page.locator('input[type="password"]:visible')
                    pwd_wait = 0
                    while await pwd.count() == 0 and pwd_wait < 10:
                        await page.wait_for_timeout(1000)
                        pwd_wait += 1
                    if await pwd.count() > 0:
                        await pwd.first.fill(MT_PASSWORD)
                        submit2 = page.locator('button[type="submit"]:visible, button:has-text("Continue"):visible, button:has-text("Log in"):visible')
                        if await submit2.count() > 0:
                            await submit2.first.click()
                            await page.wait_for_timeout(6000)

                elif cnt >= 2:
                    await visible_inputs.nth(0).fill(MT_EMAIL)
                    await visible_inputs.nth(1).fill(MT_PASSWORD)
                    submit = page.locator('button[type="submit"]:visible')
                    if await submit.count() > 0:
                        await submit.first.click()
                        await page.wait_for_timeout(6000)

                elif cnt == 0:
                    # Mungkin sudah login (cookies from previous session)
                    logger.info("No input fields found - may already be logged in")

                logger.info(f"After login, URL: {page.url}")
            except Exception as e:
                logger.warning(f"Login form error: {e}")

            # Step 2: Navigate to MULTIPLE map views at zoom 5 for full detail
            # Each view captures vessels in that region at high detail
            map_views = [
                {"name": "ASEAN", "url": "https://www.marinetraffic.com/en/ais/home/centerx:115/centery:5/zoom:5", "wait": 15},
                {"name": "India + Sri Lanka", "url": "https://www.marinetraffic.com/en/ais/home/centerx:78/centery:12/zoom:5", "wait": 12},
                {"name": "Red Sea + Gulf", "url": "https://www.marinetraffic.com/en/ais/home/centerx:45/centery:20/zoom:5", "wait": 12},
                {"name": "Australia", "url": "https://www.marinetraffic.com/en/ais/home/centerx:140/centery:-25/zoom:5", "wait": 12},
            ]

            for view in map_views:
                logger.info(f"Navigating to {view['name']} map view...")
                try:
                    await page.goto(view["url"], timeout=45000)
                except Exception as map_err:
                    logger.warning(f"{view['name']} navigation error: {map_err}, waiting anyway...")
                await page.wait_for_timeout(view["wait"] * 1000)
                logger.info(f"  {view['name']}: captured {len(raw_responses)} total tile responses so far")

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

                            # Detect SAT-AIS vessels (encoded ship_id)
                            is_sat_ais = '==' in str(ship_id) or str(row.get('SHIPNAME', '')) == '[SAT-AIS]'

                            # Skip SAT-AIS without name
                            ship_name = row.get('SHIPNAME', '')
                            if not ship_name or ship_name == '[SAT-AIS]':
                                if is_sat_ais:
                                    continue  # Skip SAT-AIS tanpa info
                                ship_name = 'Unknown'

                            # Vessel type - gunakan GT_SHIPTYPE + TYPE_NAME untuk akurasi
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

                            # Speed (MarineTraffic sends speed * 10)
                            speed_raw = row.get('SPEED')
                            try:
                                speed = round(float(speed_raw) / 10.0, 1) if speed_raw is not None else 0.0
                            except (ValueError, TypeError):
                                speed = 0.0

                            # Course
                            course_raw = row.get('COURSE')
                            try:
                                course = round(float(course_raw), 1) if course_raw is not None else None
                            except (ValueError, TypeError):
                                course = None

                            # Heading
                            heading_raw = row.get('HEADING')
                            try:
                                heading = round(float(heading_raw), 1) if heading_raw is not None else None
                            except (ValueError, TypeError):
                                heading = None

                            # Navigation status
                            status_name = row.get('STATUS_NAME', '')
                            if status_name:
                                nav_status = status_name
                            else:
                                nav_status = ""

                            # Flag
                            flag_code = row.get('FLAG', '')
                            if flag_code == '--':
                                flag_code = ''
                            flag_url = f"https://flagcdn.com/w80/{flag_code.lower()}.png" if flag_code and flag_code != '--' else None

                            # Photo URL (hanya untuk ship_id numerik)
                            has_photo = ship_id and ship_id.isdigit()
                            photo_url = f"https://www.marinetraffic.com/getAssetDefaultPhoto/?photo_size=800&asset_id={ship_id}&asset_type_id=0" if has_photo else None

                            # MMSI: tile data TIDAK menyediakan MMSI
                            # ship_id = MarineTraffic internal ID (BUKAN MMSI)
                            # mmsi diisi kosong jika tidak tersedia
                            mmsi_val = str(row.get('MMSI', ''))
                            if not mmsi_val or mmsi_val == str(ship_id):
                                mmsi_val = ''  # Tidak ada MMSI di tile data

                            # IMO: tile data TIDAK menyediakan IMO
                            imo_val = str(row.get('IMO', ''))
                            if not imo_val:
                                imo_val = ''

                            # Length & width parsing
                            length_val = row.get('LENGTH', '')
                            width_val = row.get('WIDTH', '')
                            try:
                                if length_val and int(length_val) == 0:
                                    length_val = ''
                                if width_val and int(width_val) == 0:
                                    width_val = ''
                            except (ValueError, TypeError):
                                pass

                            vessel = {
                                "ship_id": ship_id,
                                "mmsi": mmsi_val,
                                "imo": imo_val,
                                "name": ship_name,
                                "vessel_type": vessel_type,
                                "flag": flag_code,
                                "flag_url": flag_url,
                                "photo_url": photo_url,
                                "latitude": lat,
                                "longitude": lon,
                                "speed": speed,
                                "course": course,
                                "heading": heading,
                                "nav_status": nav_status,
                                "destination": row.get('DESTINATION', ''),
                                "eta": row.get('ETA', ''),
                                "length": str(length_val),
                                "width": str(width_val),
                                "dwt": row.get('DWT', ''),
                                "elapsed_min": row.get('ELAPSED', ''),
                                "is_sat_ais": is_sat_ais,
                                "mt_ship_type_code": shiptype,
                                "mt_gt_ship_type_code": gt_shiptype,
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

    logger.info(f"Scraped {len(vessels)} vessels from MarineTraffic (REAL DATA)")
    return vessels


# ===== AUTO FORWARD =====
async def auto_forward_data(vessels_data):
    """Otomatis kirim data ke endpoint yang dikonfigurasi setelah extraction"""
    try:
        config = await db.api_forward_config.find_one({"id": "main"}, {"_id": 0})
        if not config or not config.get("enabled") or not config.get("endpoint_url"):
            return

        logger.info(f"Auto-forwarding {len(vessels_data)} vessels to {config['endpoint_url']}...")

        # Bersihkan _id dan internal fields, pastikan photo_url & flag_url ada
        clean_vessels = []
        for vessel in vessels_data:
            cv = {}
            for key, val in vessel.items():
                if key == '_id' or key == 'extraction_id':
                    continue
                cv[key] = val
            clean_vessels.append(cv)

        headers = config.get("headers") or {}
        headers["Content-Type"] = "application/json"
        method = config.get("method", "POST").upper()

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "ais_extractor_marinetraffic",
            "region": COVERAGE_LABEL,
            "vessel_count": len(clean_vessels),
            "vessels": clean_vessels,
        }

        # Log fields yang dikirim untuk debugging
        if clean_vessels:
            sample_fields = list(clean_vessels[0].keys())
            logger.info(f"Forward payload fields: {sample_fields}")
            has_photo = sum(1 for v in clean_vessels if v.get('photo_url'))
            logger.info(f"Vessels with photo_url: {has_photo}/{len(clean_vessels)}")

        if method == "POST":
            resp = requests.post(config["endpoint_url"], json=payload, headers=headers, timeout=60)
        elif method == "PUT":
            resp = requests.put(config["endpoint_url"], json=payload, headers=headers, timeout=60)
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
            "fields_sent": sample_fields if clean_vessels else [],
        })

        logger.info(f"Auto-forward complete: {len(clean_vessels)} vessels → {config['endpoint_url']} (status {resp.status_code})")

    except Exception as e:
        logger.error(f"Auto-forward failed: {e}")
        try:
            await db.forward_logs.insert_one({
                "id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "endpoint": config.get("endpoint_url", "unknown") if config else "unknown",
                "status_code": 0,
                "vessels_sent": 0,
                "success": False,
                "error": str(e),
            })
        except Exception:
            pass


# ===== SCRAPER STATE =====
bot_running = False

MAX_RETRIES = 3

# ===== EXTRACTION LOGIC =====
async def run_extraction():
    start_time = time.time()
    log_id = str(uuid.uuid4())
    source = "marinetraffic"
    error_msg = None
    vessels_data = None

    try:
        # Retry logic - coba sampai MAX_RETRIES kali
        for attempt in range(1, MAX_RETRIES + 1):
            logger.info(f"Extraction attempt {attempt}/{MAX_RETRIES}...")
            try:
                vessels_data = await scrape_marinetraffic_real()
                if vessels_data and len(vessels_data) > 0:
                    logger.info(f"Attempt {attempt} success: {len(vessels_data)} vessels")
                    break
                else:
                    logger.warning(f"Attempt {attempt} returned 0 vessels")
                    vessels_data = None
            except Exception as retry_err:
                logger.warning(f"Attempt {attempt} failed: {retry_err}")
                vessels_data = None

            if attempt < MAX_RETRIES:
                wait_sec = attempt * 5
                logger.info(f"Waiting {wait_sec}s before retry...")
                await asyncio.sleep(wait_sec)

        if not vessels_data or len(vessels_data) == 0:
            raise Exception(f"No vessel data after {MAX_RETRIES} attempts. MarineTraffic may be temporarily blocking.")

        now = datetime.now(timezone.utc).isoformat()
        for v in vessels_data:
            v["id"] = str(uuid.uuid4())
            v["last_updated"] = now
            v["source"] = source
            v["extraction_id"] = log_id

        await db.vessels.delete_many({})
        if vessels_data:
            await db.vessels.insert_many(vessels_data)

        # Simpan ke history - semua field lengkap dengan timestamp
        history_docs = []
        for v in vessels_data:
            hdoc = {
                "ship_id": v.get("ship_id", ""),
                "mmsi": v.get("mmsi", ""),
                "imo": v.get("imo"),
                "name": v.get("name", "Unknown"),
                "vessel_type": v.get("vessel_type", ""),
                "flag": v.get("flag", ""),
                "flag_url": v.get("flag_url"),
                "photo_url": v.get("photo_url"),
                "latitude": v.get("latitude", 0),
                "longitude": v.get("longitude", 0),
                "speed": v.get("speed", 0),
                "course": v.get("course"),
                "heading": v.get("heading"),
                "nav_status": v.get("nav_status", ""),
                "destination": v.get("destination", ""),
                "eta": v.get("eta", ""),
                "length": v.get("length", ""),
                "width": v.get("width", ""),
                "dwt": v.get("dwt", ""),
                "extraction_id": log_id,
                "recorded_at": now,
            }
            history_docs.append(hdoc)
        if history_docs:
            await db.vessel_history.insert_many(history_docs)

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
    fieldnames = ["name", "ship_id", "mmsi", "imo", "vessel_type", "flag", "flag_url", "photo_url",
                  "latitude", "longitude", "speed", "course", "heading", "nav_status",
                  "destination", "eta", "length", "width", "dwt", "is_sat_ais",
                  "last_updated", "source"]
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
        {}, {"_id": 0, "name": 1, "mmsi": 1, "ship_id": 1, "vessel_type": 1, "latitude": 1,
             "longitude": 1, "speed": 1, "course": 1, "heading": 1, "flag": 1, "nav_status": 1,
             "destination": 1, "length": 1, "width": 1, "dwt": 1}
    ).to_list(10000)
    return {"vessels": vessels}


# ===== VESSEL TRACK HISTORY =====
@api_router.get("/vessels/{ship_id}/track")
async def get_vessel_track(
    ship_id: str,
    hours: int = Query(24, ge=1, le=720),
    user=Depends(get_current_user)
):
    """Get movement track history for a specific vessel"""
    # Calculate time cutoff
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    # Find all history points for this vessel
    track = await db.vessel_history.find(
        {"ship_id": ship_id, "recorded_at": {"$gte": cutoff}},
        {"_id": 0, "latitude": 1, "longitude": 1, "speed": 1, "course": 1,
         "heading": 1, "nav_status": 1, "recorded_at": 1}
    ).sort("recorded_at", 1).to_list(5000)

    # Get vessel info from latest data
    vessel_info = await db.vessels.find_one({"ship_id": ship_id}, {"_id": 0})
    if not vessel_info:
        # Fallback: get from latest history
        vessel_info = await db.vessel_history.find_one(
            {"ship_id": ship_id}, {"_id": 0},
            sort=[("recorded_at", -1)]
        )

    return {
        "ship_id": ship_id,
        "vessel": vessel_info,
        "track": track,
        "track_points": len(track),
        "hours_range": hours,
    }

@api_router.get("/vessels/{ship_id}/detail")
async def get_vessel_detail(ship_id: str, user=Depends(get_current_user)):
    """Get full detail of a vessel including latest position and track summary"""
    # Current position
    vessel = await db.vessels.find_one({"ship_id": ship_id}, {"_id": 0})
    if not vessel:
        vessel = await db.vessel_history.find_one(
            {"ship_id": ship_id}, {"_id": 0},
            sort=[("recorded_at", -1)]
        )
    if not vessel:
        raise HTTPException(status_code=404, detail="Vessel not found")

    # Track summary
    total_points = await db.vessel_history.count_documents({"ship_id": ship_id})
    first_seen = await db.vessel_history.find_one(
        {"ship_id": ship_id}, {"_id": 0, "recorded_at": 1},
        sort=[("recorded_at", 1)]
    )
    last_seen = await db.vessel_history.find_one(
        {"ship_id": ship_id}, {"_id": 0, "recorded_at": 1},
        sort=[("recorded_at", -1)]
    )

    return {
        "vessel": vessel,
        "track_summary": {
            "total_points": total_points,
            "first_seen": first_seen.get("recorded_at") if first_seen else None,
            "last_seen": last_seen.get("recorded_at") if last_seen else None,
        }
    }

@api_router.get("/history/search")
async def search_vessel_history(
    name: Optional[str] = None,
    mmsi: Optional[str] = None,
    ship_id: Optional[str] = None,
    hours: int = Query(24, ge=1, le=720),
    user=Depends(get_current_user)
):
    """Search vessel history by name/mmsi/ship_id"""
    query = {}
    if ship_id:
        query["ship_id"] = ship_id
    elif mmsi:
        query["mmsi"] = mmsi
    elif name:
        query["name"] = {"$regex": name, "$options": "i"}
    else:
        raise HTTPException(status_code=400, detail="Provide name, mmsi, or ship_id")

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    query["recorded_at"] = {"$gte": cutoff}

    track = await db.vessel_history.find(
        query,
        {"_id": 0, "ship_id": 1, "name": 1, "latitude": 1, "longitude": 1,
         "speed": 1, "course": 1, "heading": 1, "nav_status": 1,
         "flag": 1, "vessel_type": 1, "photo_url": 1, "flag_url": 1,
         "destination": 1, "recorded_at": 1}
    ).sort("recorded_at", 1).to_list(5000)

    return {"query": {k: v for k, v in query.items() if k != "recorded_at"}, "hours": hours, "points": len(track), "track": track}


# ====================================================================
# PHOTO PROXY - Fetch foto kapal dari MarineTraffic dan cache
# ====================================================================
from fastapi.responses import Response
import base64

@api_router.get("/photo/{ship_id}")
async def get_vessel_photo(ship_id: str):
    """Proxy foto kapal dari MarineTraffic dengan cache"""
    cached = await db.photo_cache.find_one({"ship_id": ship_id}, {"_id": 0})
    if cached and cached.get("image_data"):
        img_bytes = base64.b64decode(cached["image_data"])
        return Response(content=img_bytes, media_type=cached.get("content_type", "image/jpeg"),
                       headers={"Cache-Control": "public, max-age=86400"})
    try:
        import cloudscraper as cs_mod
        scraper_cs = cs_mod.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
        url = f"https://www.marinetraffic.com/getAssetDefaultPhoto/?photo_size=800&asset_id={ship_id}&asset_type_id=0"
        resp = scraper_cs.get(url, timeout=15)
        if resp.status_code == 200 and 'image' in resp.headers.get('content-type', ''):
            img_bytes = resp.content
            await db.photo_cache.update_one(
                {"ship_id": ship_id},
                {"$set": {
                    "ship_id": ship_id,
                    "image_data": base64.b64encode(img_bytes).decode('utf-8'),
                    "content_type": resp.headers.get('content-type', 'image/jpeg'),
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                }}, upsert=True)
            return Response(content=img_bytes, media_type="image/jpeg",
                           headers={"Cache-Control": "public, max-age=86400"})
    except Exception as e:
        logger.warning(f"Photo fetch error {ship_id}: {e}")
    pixel = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    return Response(content=pixel, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


# ====================================================================
# EXTERNAL API - Untuk digunakan aplikasi lain (tanpa login dashboard)
# Semua endpoint di bawah /api/ext/ bisa diakses aplikasi external
# ====================================================================
external_router = APIRouter(prefix="/api/ext")

@external_router.get("/")
async def ext_root():
    """API info dan daftar endpoint yang tersedia"""
    return {
        "service": "AIS Data Extractor - External API",
        "version": "2.0.0",
        "region": "ASEAN",
        "source": "MarineTraffic",
        "endpoints": {
            "GET /api/ext/vessels": "Semua kapal (posisi terkini) - params: search, vessel_type, flag, page, limit",
            "GET /api/ext/vessels/stats": "Statistik kapal (total, tipe, bendera)",
            "GET /api/ext/vessels/{ship_id}": "Detail lengkap satu kapal",
            "GET /api/ext/vessels/{ship_id}/track": "Track pergerakan kapal - params: hours (1-720)",
            "GET /api/ext/vessels/{ship_id}/history": "Semua history record kapal - params: hours, page, limit",
            "GET /api/ext/track/search": "Cari track kapal by nama/mmsi - params: name, mmsi, ship_id, hours",
            "GET /api/ext/track/multi": "Track beberapa kapal sekaligus - params: ship_ids (comma separated), hours",
            "GET /api/ext/extractions": "Log extraction terakhir",
        }
    }

@external_router.get("/vessels")
async def ext_get_vessels(
    search: Optional[str] = None,
    vessel_type: Optional[str] = None,
    flag: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=1000),
):
    """Semua kapal - posisi terkini di wilayah ASEAN"""
    query = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"mmsi": {"$regex": search, "$options": "i"}},
        ]
    if vessel_type:
        query["vessel_type"] = {"$regex": vessel_type, "$options": "i"}
    if flag:
        query["flag"] = flag.upper()

    total = await db.vessels.count_documents(query)
    skip = (page - 1) * limit
    vessels = await db.vessels.find(query, {
        "_id": 0, "extraction_id": 0
    }).skip(skip).limit(limit).to_list(limit)

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": math.ceil(total / limit) if total > 0 else 0,
        "vessels": vessels,
    }

@external_router.get("/vessels/stats")
async def ext_get_stats():
    """Statistik overview semua kapal"""
    total = await db.vessels.count_documents({})
    type_pipeline = [{"$group": {"_id": "$vessel_type", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
    type_stats = await db.vessels.aggregate(type_pipeline).to_list(50)
    flag_pipeline = [{"$group": {"_id": "$flag", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}, {"$limit": 15}]
    flag_stats = await db.vessels.aggregate(flag_pipeline).to_list(15)
    speed_pipeline = [{"$group": {"_id": None, "avg_speed": {"$avg": "$speed"}, "max_speed": {"$max": "$speed"}}}]
    speed_stats = await db.vessels.aggregate(speed_pipeline).to_list(1)

    last_log = await db.extraction_logs.find_one({"status": "success"}, {"_id": 0}, sort=[("timestamp", -1)])

    return {
        "total_vessels": total,
        "vessel_types": [{"type": t["_id"] or "Unknown", "count": t["count"]} for t in type_stats],
        "top_flags": [{"flag": f["_id"] or "N/A", "count": f["count"]} for f in flag_stats],
        "avg_speed": round(speed_stats[0]["avg_speed"], 1) if speed_stats and speed_stats[0].get("avg_speed") else 0,
        "max_speed": round(speed_stats[0]["max_speed"], 1) if speed_stats and speed_stats[0].get("max_speed") else 0,
        "last_extraction": {
            "timestamp": last_log.get("timestamp"),
            "vessels_count": last_log.get("vessels_count"),
            "source": last_log.get("source"),
        } if last_log else None,
    }

@external_router.get("/vessels/{ship_id}")
async def ext_get_vessel_detail(ship_id: str):
    """Detail lengkap satu kapal + summary track"""
    vessel = await db.vessels.find_one({"ship_id": ship_id}, {"_id": 0, "extraction_id": 0})
    if not vessel:
        vessel = await db.vessel_history.find_one(
            {"ship_id": ship_id}, {"_id": 0, "extraction_id": 0},
            sort=[("recorded_at", -1)]
        )
    if not vessel:
        raise HTTPException(status_code=404, detail=f"Vessel with ship_id '{ship_id}' not found")

    total_points = await db.vessel_history.count_documents({"ship_id": ship_id})
    first_seen = await db.vessel_history.find_one({"ship_id": ship_id}, {"_id": 0, "recorded_at": 1, "latitude": 1, "longitude": 1}, sort=[("recorded_at", 1)])
    last_seen = await db.vessel_history.find_one({"ship_id": ship_id}, {"_id": 0, "recorded_at": 1, "latitude": 1, "longitude": 1}, sort=[("recorded_at", -1)])

    return {
        "vessel": vessel,
        "track_summary": {
            "total_track_points": total_points,
            "first_seen": first_seen if first_seen else None,
            "last_seen": last_seen if last_seen else None,
        }
    }

@external_router.get("/vessels/{ship_id}/track")
async def ext_get_vessel_track(
    ship_id: str,
    hours: int = Query(168, ge=1, le=720),
):
    """Track pergerakan kapal - semua titik posisi dalam rentang waktu"""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    vessel_info = await db.vessels.find_one({"ship_id": ship_id}, {"_id": 0, "extraction_id": 0})
    if not vessel_info:
        vessel_info = await db.vessel_history.find_one(
            {"ship_id": ship_id}, {"_id": 0, "extraction_id": 0},
            sort=[("recorded_at", -1)]
        )

    track = await db.vessel_history.find(
        {"ship_id": ship_id, "recorded_at": {"$gte": cutoff}},
        {"_id": 0, "latitude": 1, "longitude": 1, "speed": 1, "course": 1,
         "heading": 1, "nav_status": 1, "destination": 1, "recorded_at": 1}
    ).sort("recorded_at", 1).to_list(10000)

    return {
        "ship_id": ship_id,
        "vessel": vessel_info,
        "hours_range": hours,
        "track_points": len(track),
        "track": track,
    }

@external_router.get("/vessels/{ship_id}/history")
async def ext_get_vessel_history(
    ship_id: str,
    hours: int = Query(720, ge=1, le=8760),
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=1000),
):
    """Semua history record kapal - data lengkap per extraction"""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    query = {"ship_id": ship_id, "recorded_at": {"$gte": cutoff}}

    total = await db.vessel_history.count_documents(query)
    skip = (page - 1) * limit
    records = await db.vessel_history.find(
        query, {"_id": 0, "extraction_id": 0}
    ).sort("recorded_at", -1).skip(skip).limit(limit).to_list(limit)

    return {
        "ship_id": ship_id,
        "hours_range": hours,
        "total": total,
        "page": page,
        "pages": math.ceil(total / limit) if total > 0 else 0,
        "records": records,
    }

@external_router.get("/track/search")
async def ext_search_track(
    name: Optional[str] = None,
    mmsi: Optional[str] = None,
    ship_id: Optional[str] = None,
    hours: int = Query(168, ge=1, le=720),
):
    """Cari track kapal berdasarkan nama, MMSI, atau ship_id"""
    query = {}
    if ship_id:
        query["ship_id"] = ship_id
    elif mmsi:
        query["mmsi"] = mmsi
    elif name:
        query["name"] = {"$regex": name, "$options": "i"}
    else:
        raise HTTPException(status_code=400, detail="Harus isi parameter: name, mmsi, atau ship_id")

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    query["recorded_at"] = {"$gte": cutoff}

    # Get unique ships matching query
    pipeline = [
        {"$match": query},
        {"$sort": {"recorded_at": -1}},
        {"$group": {
            "_id": "$ship_id",
            "name": {"$first": "$name"},
            "mmsi": {"$first": "$mmsi"},
            "vessel_type": {"$first": "$vessel_type"},
            "flag": {"$first": "$flag"},
            "flag_url": {"$first": "$flag_url"},
            "photo_url": {"$first": "$photo_url"},
            "latest_lat": {"$first": "$latitude"},
            "latest_lon": {"$first": "$longitude"},
            "latest_speed": {"$first": "$speed"},
            "latest_recorded": {"$first": "$recorded_at"},
            "track_points": {"$sum": 1},
        }},
        {"$sort": {"track_points": -1}},
        {"$limit": 20},
    ]
    results = await db.vessel_history.aggregate(pipeline).to_list(20)

    ships = []
    for r in results:
        ships.append({
            "ship_id": r["_id"],
            "name": r["name"],
            "mmsi": r["mmsi"],
            "vessel_type": r["vessel_type"],
            "flag": r["flag"],
            "flag_url": r["flag_url"],
            "photo_url": r["photo_url"],
            "latest_position": {"latitude": r["latest_lat"], "longitude": r["latest_lon"]},
            "latest_speed": r["latest_speed"],
            "latest_recorded_at": r["latest_recorded"],
            "track_points": r["track_points"],
        })

    return {
        "query": {k: v for k, v in query.items() if k != "recorded_at"},
        "hours_range": hours,
        "ships_found": len(ships),
        "ships": ships,
    }

@external_router.get("/track/multi")
async def ext_get_multi_track(
    ship_ids: str = Query(..., description="Comma-separated ship_ids, contoh: 711882,732057,214431"),
    hours: int = Query(168, ge=1, le=720),
):
    """Track beberapa kapal sekaligus - untuk visualisasi multi-vessel"""
    ids = [s.strip() for s in ship_ids.split(",") if s.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="ship_ids tidak boleh kosong")
    if len(ids) > 20:
        raise HTTPException(status_code=400, detail="Maksimal 20 kapal per request")

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    results = {}

    for sid in ids:
        vessel = await db.vessels.find_one({"ship_id": sid}, {"_id": 0, "extraction_id": 0})
        if not vessel:
            vessel = await db.vessel_history.find_one(
                {"ship_id": sid}, {"_id": 0, "extraction_id": 0},
                sort=[("recorded_at", -1)]
            )
        track = await db.vessel_history.find(
            {"ship_id": sid, "recorded_at": {"$gte": cutoff}},
            {"_id": 0, "latitude": 1, "longitude": 1, "speed": 1, "course": 1,
             "heading": 1, "recorded_at": 1}
        ).sort("recorded_at", 1).to_list(5000)

        results[sid] = {
            "vessel": vessel,
            "track_points": len(track),
            "track": track,
        }

    return {
        "hours_range": hours,
        "ships_requested": len(ids),
        "results": results,
    }

@external_router.get("/extractions")
async def ext_get_extractions(limit: int = Query(10, ge=1, le=50)):
    """Log extraction terakhir"""
    logs = await db.extraction_logs.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return {"total_shown": len(logs), "extractions": logs}


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

    vessels = await db.vessels.find({}, {"_id": 0, "extraction_id": 0}).to_list(10000)
    if not vessels:
        raise HTTPException(status_code=404, detail="No vessel data to send")

    # Log fields untuk verifikasi
    if vessels:
        sample_fields = list(vessels[0].keys())
        has_photo = sum(1 for v in vessels if v.get('photo_url'))
        logger.info(f"Manual send - Fields: {sample_fields}")
        logger.info(f"Manual send - Vessels with photo_url: {has_photo}/{len(vessels)}")

    try:
        headers = config.get("headers") or {}
        headers["Content-Type"] = "application/json"
        method = config.get("method", "POST").upper()
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "ais_extractor_marinetraffic",
            "region": COVERAGE_LABEL,
            "vessel_count": len(vessels),
            "vessels": vessels,
        }
        if method == "POST":
            resp = requests.post(config["endpoint_url"], json=payload, headers=headers, timeout=60)
        elif method == "PUT":
            resp = requests.put(config["endpoint_url"], json=payload, headers=headers, timeout=60)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported method: {method}")
        return {
            "message": "Data sent successfully",
            "status_code": resp.status_code,
            "vessels_sent": len(vessels),
            "fields_sent": sample_fields if vessels else [],
            "vessels_with_photo": has_photo if vessels else 0,
        }
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
    return {"message": "AIS Data Extractor API - MarineTraffic Real Data", "version": "3.0.0", "region": COVERAGE_LABEL, "source": "MarineTraffic"}


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
    await db.vessel_history.create_index([("ship_id", 1), ("recorded_at", -1)])
    await db.vessel_history.create_index("recorded_at")
    await db.vessel_history.create_index("name")
    logger.info("AIS Data Extractor v2 started - MarineTraffic Real Data Source")

@app.on_event("shutdown")
async def shutdown():
    if scheduler.running:
        scheduler.shutdown()
    async_client.close()

app.include_router(api_router)
app.include_router(external_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
