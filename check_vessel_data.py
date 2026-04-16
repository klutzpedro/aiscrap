#!/usr/bin/env python3

import requests
import json

def check_vessel_data():
    base_url = "https://vessel-tracker-api.preview.emergentagent.com"
    
    # Login first
    login_response = requests.post(f"{base_url}/api/auth/login", 
                                 json={"email": "admin", "password": "Paparoni83#"})
    
    if login_response.status_code != 200:
        print("❌ Login failed")
        return
    
    token = login_response.json()['token']
    headers = {'Authorization': f'Bearer {token}'}
    
    # Get vessel stats
    stats_response = requests.get(f"{base_url}/api/vessels/stats", headers=headers)
    if stats_response.status_code == 200:
        stats = stats_response.json()
        print(f"📊 Total vessels: {stats.get('total_vessels', 0)}")
        print(f"📊 Total extractions: {stats.get('total_extractions', 0)}")
        
        if stats.get('last_extraction'):
            last_ext = stats['last_extraction']
            print(f"📊 Last extraction:")
            print(f"   - Timestamp: {last_ext.get('timestamp')}")
            print(f"   - Source: {last_ext.get('source')}")
            print(f"   - Vessels count: {last_ext.get('vessels_count')}")
            print(f"   - Status: {last_ext.get('status')}")
            print(f"   - Duration: {last_ext.get('duration_seconds')}s")
    
    # Get some vessel samples
    vessels_response = requests.get(f"{base_url}/api/vessels?limit=10", headers=headers)
    if vessels_response.status_code == 200:
        vessels_data = vessels_response.json()
        vessels = vessels_data.get('vessels', [])
        print(f"\n🚢 Sample vessels ({len(vessels)} shown):")
        for i, vessel in enumerate(vessels[:5]):
            print(f"   {i+1}. {vessel.get('name', 'N/A')} - {vessel.get('vessel_type', 'N/A')} - Source: {vessel.get('source', 'N/A')}")
    
    # Get extraction logs
    logs_response = requests.get(f"{base_url}/api/bot/logs?limit=3", headers=headers)
    if logs_response.status_code == 200:
        logs_data = logs_response.json()
        logs = logs_data.get('logs', [])
        print(f"\n📋 Recent extraction logs ({len(logs)} shown):")
        for i, log in enumerate(logs):
            print(f"   {i+1}. {log.get('timestamp')} - {log.get('status')} - {log.get('source')} - {log.get('vessels_count')} vessels")

if __name__ == "__main__":
    check_vessel_data()