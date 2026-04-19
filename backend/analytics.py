"""
Maritime Intelligence & Anomaly Detection Module
For TNI AL - Naval Defense & Security Monitoring
"""
import math
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)

# ====================================================================
# STRATEGIC ZONE DEFINITIONS
# ====================================================================
STRATEGIC_ZONES = {
    "natuna": {
        "name": "Laut Natuna Utara",
        "priority": "CRITICAL",
        "description": "Zona perbatasan strategis - potensi klaim China (Nine-Dash Line)",
        "polygon": [
            (2.0, 105.0), (6.5, 105.0), (6.5, 111.0), (2.0, 111.0)
        ],
        "bbox": {"min_lat": 2.0, "max_lat": 6.5, "min_lon": 105.0, "max_lon": 111.0},
    },
    "selat_malaka": {
        "name": "Selat Malaka",
        "priority": "HIGH",
        "description": "Chokepoint pelayaran internasional tersibuk - risiko piracy",
        "polygon": [
            (0.8, 98.0), (7.0, 98.0), (7.0, 104.5), (0.8, 104.5)
        ],
        "bbox": {"min_lat": 0.8, "max_lat": 7.0, "min_lon": 98.0, "max_lon": 104.5},
    },
    "papua": {
        "name": "Perairan Papua",
        "priority": "HIGH",
        "description": "Perbatasan timur Indonesia - monitoring aktivitas asing",
        "polygon": [
            (-9.0, 130.0), (0.5, 130.0), (0.5, 141.5), (-9.0, 141.5)
        ],
        "bbox": {"min_lat": -9.0, "max_lat": 0.5, "min_lon": 130.0, "max_lon": 141.5},
    },
    "alki_1": {
        "name": "ALKI I (Sunda Strait - Karimata)",
        "priority": "HIGH",
        "description": "Alur Laut Kepulauan Indonesia I: Laut China Selatan → Selat Karimata → Selat Sunda",
        "polygon": [
            (-7.0, 104.0), (4.0, 104.0), (4.0, 108.5), (-7.0, 108.5)
        ],
        "bbox": {"min_lat": -7.0, "max_lat": 4.0, "min_lon": 104.0, "max_lon": 108.5},
    },
    "alki_2": {
        "name": "ALKI II (Lombok - Makassar)",
        "priority": "HIGH",
        "description": "Alur Laut Kepulauan Indonesia II: Laut Sulawesi → Selat Makassar → Selat Lombok",
        "polygon": [
            (-9.0, 115.0), (3.5, 115.0), (3.5, 120.5), (-9.0, 120.5)
        ],
        "bbox": {"min_lat": -9.0, "max_lat": 3.5, "min_lon": 115.0, "max_lon": 120.5},
    },
    "alki_3": {
        "name": "ALKI III (Maluku - Banda - Ombai)",
        "priority": "HIGH",
        "description": "Alur Laut Kepulauan Indonesia III: Pasifik → Laut Maluku → Laut Banda → Selat Ombai",
        "polygon": [
            (-11.0, 124.0), (3.0, 124.0), (3.0, 136.0), (-11.0, 136.0)
        ],
        "bbox": {"min_lat": -11.0, "max_lat": 3.0, "min_lon": 124.0, "max_lon": 136.0},
    },
}

def point_in_bbox(lat, lon, bbox):
    return (bbox["min_lat"] <= lat <= bbox["max_lat"] and
            bbox["min_lon"] <= lon <= bbox["max_lon"])

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ====================================================================
# ANOMALY DETECTION ALGORITHMS
# ====================================================================

def detect_speed_anomaly(vessel):
    """Deteksi kecepatan tidak wajar berdasarkan tipe kapal"""
    speed = vessel.get("speed", 0)
    vtype = (vessel.get("vessel_type") or "").lower()
    if speed is None or speed == 0:
        return None

    # Speed limits per vessel type (knots)
    limits = {
        "cargo": (0.5, 18), "tanker": (0.5, 17), "container": (0.5, 25),
        "bulk": (0.5, 16), "passenger": (0.5, 30), "fishing": (0.5, 14),
        "tug": (0.5, 15), "military": (0.5, 35),
    }
    for key, (lo, hi) in limits.items():
        if key in vtype:
            if speed > hi:
                return {
                    "type": "SPEED_ANOMALY",
                    "severity": "HIGH" if speed > hi * 1.3 else "MEDIUM",
                    "detail": f"Kecepatan {speed} kn melebihi batas normal {hi} kn untuk {vessel.get('vessel_type')}",
                    "speed": speed, "limit": hi,
                }
            break
    return None

def detect_zone_intrusion(vessel):
    """Deteksi kapal asing di zona strategis"""
    lat = vessel.get("latitude", 0)
    lon = vessel.get("longitude", 0)
    flag = vessel.get("flag", "")
    name = vessel.get("name", "")

    # Skip Indonesian vessels and SAT-AIS
    if flag == "ID" or "SAT-AIS" in name:
        return None

    intrusions = []
    for zone_id, zone in STRATEGIC_ZONES.items():
        if point_in_bbox(lat, lon, zone["bbox"]):
            severity = "CRITICAL" if zone["priority"] == "CRITICAL" and flag not in ["SG", "MY"] else "HIGH"
            intrusions.append({
                "type": "ZONE_INTRUSION",
                "severity": severity,
                "zone_id": zone_id,
                "zone_name": zone["name"],
                "detail": f"Kapal asing {vessel.get('name')} [{flag}] terdeteksi di {zone['name']}",
                "vessel_flag": flag,
            })
    return intrusions if intrusions else None


def detect_loitering(track_points, threshold_km=5, min_points=3):
    """Deteksi kapal berputar di satu area (loitering)"""
    if len(track_points) < min_points:
        return None

    # Hitung bounding box dari semua track points
    lats = [p["latitude"] for p in track_points]
    lons = [p["longitude"] for p in track_points]
    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)

    # Hitung jarak maksimum dari center
    max_dist = 0
    for p in track_points:
        d = haversine_km(center_lat, center_lon, p["latitude"], p["longitude"])
        max_dist = max(max_dist, d)

    if max_dist < threshold_km and len(track_points) >= min_points:
        return {
            "type": "LOITERING",
            "severity": "MEDIUM",
            "detail": f"Kapal berputar dalam radius {max_dist:.1f} km selama {len(track_points)} observasi",
            "center_lat": round(center_lat, 5),
            "center_lon": round(center_lon, 5),
            "radius_km": round(max_dist, 1),
            "observations": len(track_points),
        }
    return None


def detect_ais_gap(track_points, gap_threshold_min=120):
    """Deteksi gap dalam transmisi AIS (matikan AIS = dark vessel)"""
    gaps = []
    for i in range(1, len(track_points)):
        t1 = track_points[i-1].get("recorded_at", "")
        t2 = track_points[i].get("recorded_at", "")
        try:
            dt1 = datetime.fromisoformat(t1)
            dt2 = datetime.fromisoformat(t2)
            gap_min = (dt2 - dt1).total_seconds() / 60
            if gap_min > gap_threshold_min:
                # Cek apakah posisi berubah signifikan
                dist = haversine_km(
                    track_points[i-1]["latitude"], track_points[i-1]["longitude"],
                    track_points[i]["latitude"], track_points[i]["longitude"]
                )
                gaps.append({
                    "type": "AIS_GAP",
                    "severity": "HIGH" if gap_min > 360 else "MEDIUM",
                    "detail": f"AIS gap {gap_min:.0f} menit, perpindahan {dist:.1f} km (kemungkinan dark vessel)",
                    "gap_minutes": round(gap_min),
                    "distance_km": round(dist, 1),
                    "from_time": t1,
                    "to_time": t2,
                    "from_pos": {"lat": track_points[i-1]["latitude"], "lon": track_points[i-1]["longitude"]},
                    "to_pos": {"lat": track_points[i]["latitude"], "lon": track_points[i]["longitude"]},
                })
        except Exception:
            continue
    return gaps if gaps else None


def detect_position_jump(track_points, max_speed_kmh=60):
    """Deteksi lompatan posisi yang tidak mungkin (spoofing)"""
    jumps = []
    for i in range(1, len(track_points)):
        t1 = track_points[i-1].get("recorded_at", "")
        t2 = track_points[i].get("recorded_at", "")
        try:
            dt1 = datetime.fromisoformat(t1)
            dt2 = datetime.fromisoformat(t2)
            hours = (dt2 - dt1).total_seconds() / 3600
            if hours <= 0:
                continue
            dist = haversine_km(
                track_points[i-1]["latitude"], track_points[i-1]["longitude"],
                track_points[i]["latitude"], track_points[i]["longitude"]
            )
            implied_speed = dist / hours
            if implied_speed > max_speed_kmh:
                jumps.append({
                    "type": "POSITION_JUMP",
                    "severity": "CRITICAL",
                    "detail": f"Posisi melompat {dist:.0f} km dalam {hours:.1f} jam (implied {implied_speed:.0f} km/h) - kemungkinan AIS spoofing",
                    "distance_km": round(dist, 1),
                    "hours": round(hours, 2),
                    "implied_speed_kmh": round(implied_speed, 1),
                })
        except Exception:
            continue
    return jumps if jumps else None


# ====================================================================
# ZONE ANALYSIS
# ====================================================================

def analyze_zone_traffic(vessels, zone_id):
    """Analisis traffic di zona tertentu"""
    zone = STRATEGIC_ZONES.get(zone_id)
    if not zone:
        return None

    bbox = zone["bbox"]
    zone_vessels = [v for v in vessels if point_in_bbox(v.get("latitude", 0), v.get("longitude", 0), bbox)]

    # Classify by flag
    id_vessels = [v for v in zone_vessels if v.get("flag") == "ID"]
    foreign_vessels = [v for v in zone_vessels if v.get("flag") and v.get("flag") != "ID" and v.get("flag") != "N/A"]
    unknown_vessels = [v for v in zone_vessels if not v.get("flag") or v.get("flag") == "N/A"]

    # Flag distribution
    flag_dist = {}
    for v in zone_vessels:
        f = v.get("flag") or "N/A"
        flag_dist[f] = flag_dist.get(f, 0) + 1

    # Type distribution
    type_dist = {}
    for v in zone_vessels:
        t = v.get("vessel_type") or "Unknown"
        type_dist[t] = type_dist.get(t, 0) + 1

    return {
        "zone_id": zone_id,
        "zone_name": zone["name"],
        "priority": zone["priority"],
        "total_vessels": len(zone_vessels),
        "indonesian_vessels": len(id_vessels),
        "foreign_vessels": len(foreign_vessels),
        "unknown_flag": len(unknown_vessels),
        "flag_distribution": dict(sorted(flag_dist.items(), key=lambda x: -x[1])),
        "type_distribution": dict(sorted(type_dist.items(), key=lambda x: -x[1])),
        "foreign_vessel_list": [
            {"name": v.get("name"), "flag": v.get("flag"), "type": v.get("vessel_type"),
             "lat": v.get("latitude"), "lon": v.get("longitude"), "speed": v.get("speed"),
             "ship_id": v.get("ship_id")}
            for v in foreign_vessels[:50]
        ],
    }


# ====================================================================
# FULL ANALYSIS RUNNER
# ====================================================================

async def run_full_analysis(db, vessels):
    """Jalankan semua analisis pada data vessel terkini"""
    analysis_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    alerts = []

    # 1. Zone traffic analysis
    zone_reports = {}
    for zone_id in STRATEGIC_ZONES:
        zone_reports[zone_id] = analyze_zone_traffic(vessels, zone_id)

    # 2. Anomaly detection per vessel
    speed_anomalies = []
    zone_intrusions = []
    for v in vessels:
        # Speed anomaly
        sa = detect_speed_anomaly(v)
        if sa:
            sa["vessel"] = {"name": v.get("name"), "ship_id": v.get("ship_id"),
                           "flag": v.get("flag"), "type": v.get("vessel_type"),
                           "lat": v.get("latitude"), "lon": v.get("longitude")}
            speed_anomalies.append(sa)

        # Zone intrusion
        zi = detect_zone_intrusion(v)
        if zi:
            for z in zi:
                z["vessel"] = {"name": v.get("name"), "ship_id": v.get("ship_id"),
                              "flag": v.get("flag"), "type": v.get("vessel_type"),
                              "lat": v.get("latitude"), "lon": v.get("longitude")}
                zone_intrusions.append(z)

    # 3. Track-based analysis (loitering, AIS gap, position jump)
    loitering_alerts = []
    ais_gaps = []
    position_jumps = []

    # Get vessels with track history
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    tracked_ships = await db.vessel_history.aggregate([
        {"$match": {"recorded_at": {"$gte": cutoff}}},
        {"$group": {"_id": "$ship_id", "count": {"$sum": 1}}},
        {"$match": {"count": {"$gte": 3}}},
        {"$limit": 200}
    ]).to_list(200)

    for ship in tracked_ships:
        sid = ship["_id"]
        track = await db.vessel_history.find(
            {"ship_id": sid, "recorded_at": {"$gte": cutoff}},
            {"_id": 0, "latitude": 1, "longitude": 1, "speed": 1, "recorded_at": 1,
             "name": 1, "flag": 1, "vessel_type": 1, "ship_id": 1}
        ).sort("recorded_at", 1).to_list(100)

        if len(track) < 2:
            continue

        vessel_info = {"name": track[-1].get("name"), "ship_id": sid,
                      "flag": track[-1].get("flag"), "type": track[-1].get("vessel_type")}

        # Loitering
        lt = detect_loitering(track)
        if lt:
            lt["vessel"] = vessel_info
            loitering_alerts.append(lt)

        # AIS gaps
        ag = detect_ais_gap(track)
        if ag:
            for g in ag:
                g["vessel"] = vessel_info
                ais_gaps.append(g)

        # Position jumps
        pj = detect_position_jump(track)
        if pj:
            for j in pj:
                j["vessel"] = vessel_info
                position_jumps.append(j)

    # Compile all alerts
    all_anomalies = speed_anomalies + zone_intrusions + loitering_alerts + ais_gaps + position_jumps
    # Sort by severity
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    all_anomalies.sort(key=lambda x: severity_order.get(x.get("severity", "LOW"), 3))

    # Summary counts
    summary = {
        "total_vessels_analyzed": len(vessels),
        "total_anomalies": len(all_anomalies),
        "critical": sum(1 for a in all_anomalies if a.get("severity") == "CRITICAL"),
        "high": sum(1 for a in all_anomalies if a.get("severity") == "HIGH"),
        "medium": sum(1 for a in all_anomalies if a.get("severity") == "MEDIUM"),
        "speed_anomalies": len(speed_anomalies),
        "zone_intrusions": len(zone_intrusions),
        "loitering_detected": len(loitering_alerts),
        "ais_gaps": len(ais_gaps),
        "position_jumps": len(position_jumps),
    }

    # Store analysis result
    analysis_doc = {
        "id": analysis_id,
        "timestamp": now,
        "summary": summary,
        "zone_reports": zone_reports,
        "anomalies": all_anomalies[:200],  # Limit stored anomalies
    }
    await db.analytics.insert_one(analysis_doc)

    logger.info(f"Analysis complete: {summary['total_anomalies']} anomalies "
                f"({summary['critical']} CRITICAL, {summary['high']} HIGH)")

    return analysis_doc
