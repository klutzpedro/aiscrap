from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Query
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
import os
import logging
import uuid
import math
import time
import random
import io
import csv
import json
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
import bcrypt
import jwt
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bs4 import BeautifulSoup

# ===== CONFIG =====
mongo_url = os.environ['MONGO_URL']
db_name = os.environ['DB_NAME']
async_client = AsyncIOMotorClient(mongo_url)
db = async_client[db_name]
sync_client = MongoClient(mongo_url)
sync_db = sync_client[db_name]

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALGORITHM = "HS256"
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
MT_EMAIL = os.environ.get('MT_EMAIL', '')
MT_PASSWORD = os.environ.get('MT_PASSWORD', '')

ASEAN_BBOX = {"min_lat": -11.0, "max_lat": 25.0, "min_lon": 95.0, "max_lon": 150.0}

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

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str

class VesselResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    mmsi: str
    imo: Optional[str] = None
    name: str
    vessel_type: str
    flag: Optional[str] = None
    latitude: float
    longitude: float
    speed: Optional[float] = None
    course: Optional[float] = None
    heading: Optional[float] = None
    nav_status: Optional[str] = None
    destination: Optional[str] = None
    eta: Optional[str] = None
    last_updated: str
    source: str

class BotStatusResponse(BaseModel):
    running: bool
    interval_minutes: int
    last_extraction: Optional[str] = None
    next_extraction: Optional[str] = None
    total_extractions: int
    mt_connected: bool

class ExtractionLogResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    timestamp: str
    status: str
    source: str
    vessels_count: int
    duration_seconds: float
    error_message: Optional[str] = None

class ForwardConfig(BaseModel):
    endpoint_url: str
    method: str = "POST"
    headers: Optional[dict] = None
    enabled: bool = True

# ===== MARINE TRAFFIC SCRAPER =====
class MarineTrafficScraper:
    BASE_URL = "https://www.marinetraffic.com"

    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.session = None
        self.logged_in = False

    def _create_session(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
        })

    def login(self) -> bool:
        try:
            self._create_session()
            login_page = self.session.get(f"{self.BASE_URL}/en/users/login", timeout=15)
            soup = BeautifulSoup(login_page.text, 'lxml')
            token_input = soup.find('input', {'name': '_token'})
            csrf_token = token_input['value'] if token_input else ''

            login_data = {
                'email': self.email,
                'password': self.password,
                '_token': csrf_token,
            }
            self.session.headers.update({
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Referer': f"{self.BASE_URL}/en/users/login",
            })
            response = self.session.post(
                f"{self.BASE_URL}/en/users/ajax_login",
                data=login_data,
                timeout=15,
                allow_redirects=False
            )
            if response.status_code in [200, 302]:
                try:
                    data = response.json()
                    self.logged_in = data.get('success', False) or data.get('status', '') == 'ok'
                except Exception:
                    self.logged_in = response.status_code == 200
            logger.info(f"MarineTraffic login: {'success' if self.logged_in else 'failed'} (status={response.status_code})")
            return self.logged_in
        except Exception as e:
            logger.error(f"MarineTraffic login error: {e}")
            return False

    def _lat_lon_to_tile(self, lat, lon, zoom):
        n = 2 ** zoom
        x = int((lon + 180.0) / 360.0 * n)
        lat_rad = math.radians(lat)
        y = int((1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
        return x, y

    def _get_tiles_for_bbox(self, min_lat, min_lon, max_lat, max_lon, zoom):
        tiles = set()
        x1, y1 = self._lat_lon_to_tile(max_lat, min_lon, zoom)
        x2, y2 = self._lat_lon_to_tile(min_lat, max_lon, zoom)
        for x in range(min(x1, x2), max(x1, x2) + 1):
            for y in range(min(y1, y2), max(y1, y2) + 1):
                tiles.add((x, y))
        return list(tiles)

    def fetch_vessels(self, bbox=None):
        if bbox is None:
            bbox = ASEAN_BBOX
        if not self.logged_in:
            self.login()

        vessels = []
        try:
            zoom = 5
            tiles = self._get_tiles_for_bbox(bbox['min_lat'], bbox['min_lon'], bbox['max_lat'], bbox['max_lon'], zoom)
            logger.info(f"Fetching {len(tiles)} tiles at zoom {zoom}")

            self.session.headers.update({
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'X-Requested-With': 'XMLHttpRequest',
            })

            for tx, ty in tiles[:20]:
                try:
                    url = f"{self.BASE_URL}/getData/get_data_json_4/z:{zoom}/X:{tx}/Y:{ty}/station:0/{int(time.time())}"
                    resp = self.session.get(url, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, dict) and 'data' in data:
                            rows = data.get('data', {}).get('rows', [])
                        elif isinstance(data, list):
                            rows = data
                        else:
                            rows = []
                        for row in rows:
                            vessel = self._parse_vessel_row(row)
                            if vessel:
                                vessels.append(vessel)
                    time.sleep(0.3)
                except Exception as e:
                    logger.warning(f"Tile {tx},{ty} error: {e}")
                    continue

            if vessels:
                logger.info(f"Scraped {len(vessels)} vessels from MarineTraffic")
            return vessels if vessels else None
        except Exception as e:
            logger.error(f"Fetch vessels error: {e}")
            return None

    def _parse_vessel_row(self, row):
        try:
            if isinstance(row, dict):
                lat = float(row.get('LAT', row.get('lat', 0)))
                lon = float(row.get('LON', row.get('lon', 0)))
                if lat == 0 and lon == 0:
                    return None
                return {
                    "mmsi": str(row.get('MMSI', row.get('mmsi', ''))),
                    "imo": str(row.get('IMO', row.get('imo', ''))) or None,
                    "name": row.get('SHIPNAME', row.get('shipname', 'Unknown')),
                    "vessel_type": self._map_ship_type(row.get('SHIPTYPE', row.get('ship_type', 0))),
                    "flag": row.get('FLAG', row.get('flag', '')),
                    "latitude": lat,
                    "longitude": lon,
                    "speed": float(row.get('SPEED', row.get('speed', 0))) / 10.0,
                    "course": float(row.get('COURSE', row.get('course', 0))),
                    "heading": float(row.get('HEADING', row.get('heading', 0))),
                    "nav_status": row.get('STATUS', row.get('status', 'N/A')),
                    "destination": row.get('DESTINATION', row.get('destination', '')),
                    "eta": row.get('ETA', row.get('eta', '')),
                }
            elif isinstance(row, (list, tuple)):
                return {
                    "mmsi": str(row[0]) if len(row) > 0 else '',
                    "name": str(row[7]) if len(row) > 7 else 'Unknown',
                    "latitude": float(row[1]) / 600000.0 if len(row) > 1 else 0,
                    "longitude": float(row[2]) / 600000.0 if len(row) > 2 else 0,
                    "speed": float(row[3]) / 10.0 if len(row) > 3 else 0,
                    "course": float(row[4]) if len(row) > 4 else 0,
                    "heading": float(row[5]) if len(row) > 5 else 0,
                    "vessel_type": self._map_ship_type(row[6] if len(row) > 6 else 0),
                    "flag": str(row[8]) if len(row) > 8 else '',
                }
            return None
        except Exception:
            return None

    def _map_ship_type(self, type_code):
        try:
            code = int(type_code)
        except (ValueError, TypeError):
            return str(type_code) if type_code else "Unknown"
        type_map = {
            (60, 69): "Passenger", (70, 79): "Cargo", (80, 89): "Tanker",
            (40, 49): "High Speed Craft", (50, 59): "Special Craft",
            (30, 35): "Fishing", (36, 37): "Sailing/Pleasure",
        }
        for (lo, hi), name in type_map.items():
            if lo <= code <= hi:
                return name
        if code == 0:
            return "Unknown"
        return f"Type {code}"


# ===== SIMULATION DATA =====
VESSEL_NAMES = [
    "PACIFIC VOYAGER", "ASIAN GLORY", "STRAIT SPIRIT", "OCEAN DIAMOND",
    "SINGAPORE STAR", "MALACCA EXPRESS", "JAKARTA PRIDE", "MANILA TRADER",
    "THAI FORTUNE", "SAIGON PEARL", "BORNEO CARRIER", "CELEBES WIND",
    "MINDANAO BREEZE", "JAVA PIONEER", "SUMATRA LEGACY", "MEKONG DELTA",
    "ANDAMAN SEA", "CORAL PRINCESS", "DRAGON PEARL", "EASTERN HORIZON",
    "GOLDEN BRIDGE", "HARMONY SEAS", "INDOCHINA STAR", "JADE EMPRESS",
    "KALIMANTAN GLORY", "LUZON EXPRESS", "MALAY SPIRIT", "NUSANTARA PRIDE",
    "ORIENTAL DAWN", "PALAWAN VOYAGER", "RED PHOENIX", "SIAM TREASURE",
    "TIMOR NAVIGATOR", "UNITY STAR", "VISAYAS CARRIER", "WEST WIND",
    "YANG MING VALOR", "ZEUS MARITIME", "BLUE HORIZON", "CRYSTAL BAY",
    "DELTA FORTUNE", "EMERALD TIDE", "FALCON SPIRIT", "GULF STAR",
    "HORIZON GLORY", "ISLAND QUEEN", "JUBILEE SEAS", "KING FISHER",
    "LIBERTY WAVE", "MERCURY TRADER", "NEPTUNE GRACE", "OLYMPIA DREAM",
    "PEARL RIVER", "QUANTUM SEAS", "ROYAL ORCHID", "SAPPHIRE SKY",
    "THUNDER BAY", "UNICORN STAR", "VICTORIA PEAK", "WONDER MAIDEN",
    "XPRESS JAVA", "YAMATO SPIRIT", "ZENITH STAR", "ALPHA MARINE",
    "BETA CARRIER", "COSMIC WAVE", "DAWN TREADER", "ECLIPSE STAR",
    "FLORA MARITIME", "GENESIS GLORY", "HARBOR LIGHT", "IVORY COAST",
    "JADEITE STAR", "KELVIN WAVE", "LOTUS DREAM", "MONSOON PRIDE",
    "NOBLE SPIRIT", "OASIS TRADER", "PIONEER SEAS", "QUEST HORIZON",
]

VESSEL_TYPES = ["Cargo", "Tanker", "Container Ship", "Bulk Carrier", "Passenger", "Fishing", "Tug", "High Speed Craft", "Supply Vessel", "General Cargo"]
FLAGS = ["SG", "MY", "ID", "PH", "TH", "VN", "MM", "PA", "LR", "MH", "HK", "JP", "CN", "KR", "TW"]
NAV_STATUSES = ["Under way using engine", "At anchor", "Moored", "Under way sailing", "Restricted maneuverability", "Not under command"]
DESTINATIONS = ["SGSIN", "MYPKG", "IDTPP", "PHMNL", "THBKK", "VNSGN", "MMRGN", "IDJKT", "IDSBY", "MYSUB", "PHCEB", "THSRI", "VNHPH", "MYPEN", "IDBLW"]

SHIPPING_LANES = [
    {"name": "Malacca Strait", "lat": (1.5, 5.5), "lon": (99.5, 103.5)},
    {"name": "Singapore Strait", "lat": (1.1, 1.4), "lon": (103.5, 104.3)},
    {"name": "South China Sea North", "lat": (10, 18), "lon": (109, 118)},
    {"name": "South China Sea South", "lat": (3, 10), "lon": (105, 115)},
    {"name": "Java Sea", "lat": (-6.5, -3), "lon": (106, 115)},
    {"name": "Makassar Strait", "lat": (-3, 1), "lon": (117, 120)},
    {"name": "Gulf of Thailand", "lat": (7, 13), "lon": (99, 104)},
    {"name": "Sulu Sea", "lat": (5, 10), "lon": (119, 123)},
    {"name": "Banda Sea", "lat": (-6, -2), "lon": (125, 132)},
    {"name": "Philippine Sea", "lat": (10, 18), "lon": (120, 127)},
    {"name": "Andaman Sea", "lat": (5, 14), "lon": (95, 99)},
    {"name": "Flores Sea", "lat": (-8, -5), "lon": (118, 125)},
]

def generate_simulation_data(count=120):
    vessels = []
    used_names = set()
    used_mmsi = set()
    flag_mmsi_prefix = {"SG": "563", "MY": "533", "ID": "525", "PH": "548", "TH": "567", "VN": "574", "MM": "506", "PA": "352", "LR": "636", "MH": "538", "HK": "477", "JP": "431", "CN": "413", "KR": "440", "TW": "416"}

    for i in range(count):
        lane = random.choice(SHIPPING_LANES)
        flag = random.choice(FLAGS)
        prefix = flag_mmsi_prefix.get(flag, "999")
        mmsi = prefix + str(random.randint(100000, 999999))
        while mmsi in used_mmsi:
            mmsi = prefix + str(random.randint(100000, 999999))
        used_mmsi.add(mmsi)

        name = random.choice(VESSEL_NAMES)
        suffix = ""
        if name in used_names:
            suffix = f" {random.choice(['I','II','III','IV','V'])}"
        used_names.add(name + suffix)

        lat = round(random.uniform(lane["lat"][0], lane["lat"][1]), 5)
        lon = round(random.uniform(lane["lon"][0], lane["lon"][1]), 5)

        vessels.append({
            "mmsi": mmsi,
            "imo": str(random.randint(1000000, 9999999)),
            "name": name + suffix,
            "vessel_type": random.choice(VESSEL_TYPES),
            "flag": flag,
            "latitude": lat,
            "longitude": lon,
            "speed": round(random.uniform(0, 18), 1),
            "course": round(random.uniform(0, 360), 1),
            "heading": round(random.uniform(0, 360), 1),
            "nav_status": random.choice(NAV_STATUSES),
            "destination": random.choice(DESTINATIONS),
            "eta": (datetime.now(timezone.utc) + timedelta(hours=random.randint(6, 240))).isoformat(),
        })
    return vessels


# ===== SCRAPER INSTANCE =====
scraper = MarineTrafficScraper(MT_EMAIL, MT_PASSWORD) if MT_EMAIL else None
bot_running = False


# ===== EXTRACTION LOGIC =====
async def run_extraction():
    global scraper
    start_time = time.time()
    log_id = str(uuid.uuid4())
    source = "simulation"
    error_msg = None
    vessels_data = None

    try:
        if scraper and MT_EMAIL:
            logger.info("Attempting MarineTraffic scrape...")
            vessels_data = scraper.fetch_vessels(ASEAN_BBOX)
            if vessels_data:
                source = "marinetraffic"
                logger.info(f"Got {len(vessels_data)} vessels from MarineTraffic")

        if not vessels_data:
            logger.info("Using simulation data")
            vessels_data = generate_simulation_data(random.randint(80, 150))
            source = "simulation"

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
        logger.info(f"Extraction complete: {len(vessels_data)} vessels ({source}) in {duration}s")

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
    fieldnames = ["name", "mmsi", "imo", "vessel_type", "flag", "latitude", "longitude", "speed", "course", "heading", "nav_status", "destination", "eta", "last_updated", "source"]
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
    vessels = await db.vessels.find({}, {"_id": 0, "name": 1, "mmsi": 1, "vessel_type": 1, "latitude": 1, "longitude": 1, "speed": 1, "course": 1, "flag": 1, "nav_status": 1}).to_list(5000)
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
        "mt_connected": scraper.logged_in if scraper else False,
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
            "source": "ais_extractor",
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


# ===== HEALTH =====
@api_router.get("/")
async def root():
    return {"message": "AIS Data Extractor API", "version": "1.0.0", "region": "ASEAN"}


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
        logger.info("Admin password updated")

    with open("/app/memory/test_credentials.md", "w") as f:
        f.write(f"# Test Credentials\n\n## Admin\n- Email: {ADMIN_EMAIL}\n- Password: {ADMIN_PASSWORD}\n- Role: admin\n\n## Auth Endpoints\n- POST /api/auth/login\n- GET /api/auth/me\n- POST /api/auth/logout\n")

@app.on_event("startup")
async def startup():
    await seed_admin()
    await db.users.create_index("email", unique=True)
    await db.vessels.create_index("mmsi")
    await db.extraction_logs.create_index("timestamp")
    logger.info("AIS Data Extractor started")

@app.on_event("shutdown")
async def shutdown():
    if scheduler.running:
        scheduler.shutdown()
    async_client.close()
    sync_client.close()

app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
