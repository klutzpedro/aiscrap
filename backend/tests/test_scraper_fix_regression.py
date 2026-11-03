# Regression tests for MarineTraffic scraper fix (PLAYWRIGHT_BROWSERS_PATH) + bot/vessels/analytics schedule
import os
import subprocess
from datetime import datetime, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "admin", "password": "Paparoni83#"}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}")
    data = r.json()
    t = data.get("token") or data.get("access_token")
    assert t
    return t


@pytest.fixture(scope="module")
def h(token):
    return {"Authorization": f"Bearer {token}"}


def _parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


# Auth
def test_login_returns_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "admin", "password": "Paparoni83#"}, timeout=30)
    assert r.status_code == 200
    d = r.json()
    print("login keys:", list(d.keys()))
    assert "token" in d and d["user"]["role"] == "admin"


def test_extract_now_requires_auth():
    r = requests.post(f"{BASE_URL}/api/bot/extract-now", timeout=30)
    assert r.status_code in (401, 403)


# Extraction (scraper fix)
class TestExtraction:
    def test_extract_now(self, h):
        r = requests.post(f"{BASE_URL}/api/bot/extract-now", headers=h, timeout=240)
        print("extract-now:", r.status_code, r.text[:300])
        assert r.status_code == 200
        assert r.json()["message"] == "Extraction completed"

    def test_last_log_success(self, h):
        r = requests.get(f"{BASE_URL}/api/bot/logs", headers=h, timeout=30)
        assert r.status_code == 200
        log = r.json()["logs"][0]
        print("last log:", {k: log.get(k) for k in ("status", "vessels_count", "duration_seconds", "error", "timestamp")})
        assert log["status"] == "success"
        assert log["vessels_count"] > 1000
        age = (datetime.now(timezone.utc) - _parse(log["timestamp"])).total_seconds()
        assert age < 300

    def test_bot_status(self, h):
        r = requests.get(f"{BASE_URL}/api/bot/status", headers=h, timeout=30)
        assert r.status_code == 200
        d = r.json()
        print("status:", d)
        assert d["mt_connected"] is True
        assert d["last_extraction"]
        assert (datetime.now(timezone.utc) - _parse(d["last_extraction"])).total_seconds() < 300

    def test_vessels_total(self, h):
        r = requests.get(f"{BASE_URL}/api/vessels", headers=h, timeout=60)
        assert r.status_code == 200
        d = r.json()
        print("vessels total:", d["total"])
        assert d["total"] > 1000
        assert len(d["vessels"]) == 50
        assert "_id" not in d["vessels"][0]
        assert d["vessels"][0].get("mmsi") is not None

    def test_backend_logs_no_playwright_missing(self):
        out = subprocess.run("tail -n 400 /var/log/supervisor/backend.*.log", shell=True, capture_output=True, text=True).stdout
        assert "Executable doesn't exist" not in out
        assert "playwright install" not in out


# Analytics schedule regression
class TestAnalyticsSchedule:
    def test_get_schedule(self, h):
        r = requests.get(f"{BASE_URL}/api/analytics/schedule", headers=h, timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("enabled", "interval_minutes", "next_run"):
            assert k in d
        assert "_id" not in d

    def test_enable_schedule_then_get(self, h):
        before = requests.get(f"{BASE_URL}/api/analytics/schedule", headers=h, timeout=30).json()
        r = requests.post(f"{BASE_URL}/api/analytics/schedule", headers=h, json={"enabled": True, "interval_minutes": 60}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["enabled"] is True and d["interval_minutes"] == 60 and d["next_run"]
        g = requests.get(f"{BASE_URL}/api/analytics/schedule", headers=h, timeout=30).json()
        assert g["enabled"] is True and g["interval_minutes"] == 60 and g["next_run"]
        # restore previous state
        requests.post(f"{BASE_URL}/api/analytics/schedule", headers=h,
                      json={"enabled": before.get("enabled", False), "interval_minutes": before.get("interval_minutes", 60)}, timeout=30)

    def test_schedule_invalid_interval(self, h):
        r = requests.post(f"{BASE_URL}/api/analytics/schedule", headers=h, json={"enabled": True, "interval_minutes": 0}, timeout=30)
        assert r.status_code == 400
