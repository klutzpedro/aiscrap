#!/usr/bin/env python3

import requests
import sys
import json
import time
from datetime import datetime

class VesselTrackerAPITester:
    def __init__(self, base_url="https://vessel-tracker-api.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.session = requests.Session()

    def log(self, message, status="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {status}: {message}")

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        
        if self.token:
            test_headers['Authorization'] = f'Bearer {self.token}'
        
        if headers:
            test_headers.update(headers)

        self.tests_run += 1
        self.log(f"Testing {name}...")
        
        try:
            if method == 'GET':
                response = self.session.get(url, headers=test_headers, timeout=30)
            elif method == 'POST':
                response = self.session.post(url, json=data, headers=test_headers, timeout=30)
            elif method == 'PUT':
                response = self.session.put(url, json=data, headers=test_headers, timeout=30)
            else:
                self.log(f"Unsupported method: {method}", "ERROR")
                return False, {}

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"✅ {name} - Status: {response.status_code}", "PASS")
            else:
                self.log(f"❌ {name} - Expected {expected_status}, got {response.status_code}", "FAIL")
                if response.text:
                    self.log(f"Response: {response.text[:200]}", "ERROR")

            try:
                response_data = response.json() if response.content else {}
            except:
                response_data = {}

            return success, response_data

        except Exception as e:
            self.log(f"❌ {name} - Error: {str(e)}", "ERROR")
            return False, {}

    def test_health_check(self):
        """Test basic API health"""
        return self.run_test("Health Check", "GET", "", 200)

    def test_login(self):
        """Test admin login"""
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "auth/login",
            200,
            data={"email": "admin", "password": "Paparoni83#"}
        )
        if success and 'token' in response:
            self.token = response['token']
            self.log(f"✅ Login successful, token acquired", "PASS")
            return True
        else:
            self.log(f"❌ Login failed - no token in response", "FAIL")
            return False

    def test_auth_me(self):
        """Test get current user"""
        return self.run_test("Get Current User", "GET", "auth/me", 200)

    def test_vessel_stats(self):
        """Test vessel statistics"""
        return self.run_test("Vessel Stats", "GET", "vessels/stats", 200)

    def test_vessels_list(self):
        """Test vessels listing"""
        return self.run_test("Vessels List", "GET", "vessels?page=1&limit=10", 200)

    def test_vessels_search(self):
        """Test vessel search"""
        return self.run_test("Vessel Search", "GET", "vessels?search=PACIFIC", 200)

    def test_vessel_types(self):
        """Test get vessel types"""
        return self.run_test("Vessel Types", "GET", "vessels/types", 200)

    def test_vessel_flags(self):
        """Test get vessel flags"""
        return self.run_test("Vessel Flags", "GET", "vessels/flags", 200)

    def test_vessels_map(self):
        """Test vessels for map"""
        return self.run_test("Vessels Map Data", "GET", "vessels/map", 200)

    def test_bot_status(self):
        """Test bot status"""
        return self.run_test("Bot Status", "GET", "bot/status", 200)

    def test_extraction_logs(self):
        """Test extraction logs"""
        return self.run_test("Extraction Logs", "GET", "bot/logs?page=1&limit=5", 200)

    def test_extract_now(self):
        """Test manual extraction"""
        self.log("Testing manual extraction (this may take 10-15 seconds)...")
        success, response = self.run_test("Extract Now", "POST", "bot/extract-now", 200)
        if success:
            # Wait a moment for extraction to complete
            time.sleep(2)
            # Verify vessels were extracted
            vessels_success, vessels_data = self.run_test("Verify Extraction", "GET", "vessels/stats", 200)
            if vessels_success and vessels_data.get('total_vessels', 0) > 0:
                self.log(f"✅ Extraction successful - {vessels_data.get('total_vessels', 0)} vessels found", "PASS")
                return True
        return success

    def test_csv_export(self):
        """Test CSV export"""
        url = f"{self.base_url}/api/vessels/export/csv"
        headers = {'Authorization': f'Bearer {self.token}'} if self.token else {}
        
        self.tests_run += 1
        self.log("Testing CSV Export...")
        
        try:
            response = self.session.get(url, headers=headers, timeout=30)
            success = response.status_code == 200
            
            if success:
                self.tests_passed += 1
                content_type = response.headers.get('content-type', '')
                if 'csv' in content_type or 'text' in content_type:
                    self.log(f"✅ CSV Export - Status: {response.status_code}, Content-Type: {content_type}", "PASS")
                    return True
                else:
                    self.log(f"⚠️ CSV Export - Wrong content type: {content_type}", "WARN")
            else:
                self.log(f"❌ CSV Export - Status: {response.status_code}", "FAIL")
            
            return success
        except Exception as e:
            self.log(f"❌ CSV Export - Error: {str(e)}", "ERROR")
            return False

    def test_forward_config(self):
        """Test API forwarding config"""
        # Get config
        get_success, _ = self.run_test("Get Forward Config", "GET", "forward/config", 200)
        
        # Update config
        config_data = {
            "endpoint_url": "https://httpbin.org/post",
            "method": "POST",
            "headers": {"X-Test": "true"},
            "enabled": True
        }
        post_success, _ = self.run_test("Update Forward Config", "POST", "forward/config", 200, data=config_data)
        
        return get_success and post_success

    def test_bot_controls(self):
        """Test bot start/stop controls"""
        # Test bot start
        start_success, _ = self.run_test("Start Bot", "POST", "bot/start", 200)
        
        # Wait a moment
        time.sleep(1)
        
        # Test bot stop
        stop_success, _ = self.run_test("Stop Bot", "POST", "bot/stop", 200)
        
        return start_success and stop_success

    def test_bot_settings(self):
        """Test bot interval settings"""
        return self.run_test("Update Bot Settings", "POST", "bot/settings?interval_minutes=45", 200)

    def test_logout(self):
        """Test logout"""
        return self.run_test("Logout", "POST", "auth/logout", 200)

    def run_all_tests(self):
        """Run all API tests"""
        self.log("🚀 Starting Vessel Tracker API Tests", "START")
        self.log(f"Testing against: {self.base_url}")
        
        # Test sequence
        tests = [
            ("Health Check", self.test_health_check),
            ("Admin Login", self.test_login),
            ("Get Current User", self.test_auth_me),
            ("Vessel Statistics", self.test_vessel_stats),
            ("Vessels List", self.test_vessels_list),
            ("Vessel Search", self.test_vessels_search),
            ("Vessel Types", self.test_vessel_types),
            ("Vessel Flags", self.test_vessel_flags),
            ("Vessels Map Data", self.test_vessels_map),
            ("Bot Status", self.test_bot_status),
            ("Extraction Logs", self.test_extraction_logs),
            ("Manual Extraction", self.test_extract_now),
            ("CSV Export", self.test_csv_export),
            ("Forward Config", self.test_forward_config),
            ("Bot Controls", self.test_bot_controls),
            ("Bot Settings", self.test_bot_settings),
            ("Logout", self.test_logout),
        ]
        
        failed_tests = []
        
        for test_name, test_func in tests:
            try:
                success = test_func()
                if not success:
                    failed_tests.append(test_name)
            except Exception as e:
                self.log(f"❌ {test_name} - Exception: {str(e)}", "ERROR")
                failed_tests.append(test_name)
            
            # Small delay between tests
            time.sleep(0.5)
        
        # Print summary
        self.log("=" * 60, "SUMMARY")
        self.log(f"Tests Run: {self.tests_run}")
        self.log(f"Tests Passed: {self.tests_passed}")
        self.log(f"Tests Failed: {self.tests_run - self.tests_passed}")
        self.log(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if failed_tests:
            self.log(f"Failed Tests: {', '.join(failed_tests)}", "FAIL")
            return False
        else:
            self.log("🎉 All tests passed!", "SUCCESS")
            return True

def main():
    tester = VesselTrackerAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())