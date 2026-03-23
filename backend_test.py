#!/usr/bin/env python3
"""
Backend API Testing for Voice Agent - Romanian TTS Optimization
Tests the optimized ElevenLabs TTS settings for natural Romanian speech
"""

import requests
import sys
import json
from datetime import datetime
from typing import Dict, Any

class VoiceAgentAPITester:
    def __init__(self, base_url: str = "https://vocal-ai-18.preview.emergentagent.com"):
        self.base_url = base_url.rstrip('/')
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name: str, success: bool, details: Dict[str, Any] = None):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
        
        result = {
            "test_name": name,
            "success": success,
            "timestamp": datetime.now().isoformat(),
            "details": details or {}
        }
        self.test_results.append(result)
        
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status} - {name}")
        if details:
            for key, value in details.items():
                print(f"  {key}: {value}")
        print()

    def run_test(self, name: str, method: str, endpoint: str, expected_status: int = 200, 
                 data: Dict = None, headers: Dict = None) -> tuple[bool, Dict]:
        """Run a single API test"""
        url = f"{self.base_url}{endpoint}"
        default_headers = {'Content-Type': 'application/json'}
        if headers:
            default_headers.update(headers)

        print(f"🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=default_headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=default_headers, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            response_data = {}
            
            try:
                response_data = response.json()
            except:
                response_data = {"raw_response": response.text[:500]}

            details = {
                "status_code": response.status_code,
                "expected_status": expected_status,
                "response_size": len(response.text),
                "response_preview": str(response_data)[:200] + "..." if len(str(response_data)) > 200 else str(response_data)
            }

            self.log_test(name, success, details)
            return success, response_data

        except Exception as e:
            details = {
                "error": str(e),
                "error_type": type(e).__name__
            }
            self.log_test(name, False, details)
            return False, {}

    def test_health_endpoint(self) -> bool:
        """Test /api/health endpoint returns proper voice configuration"""
        success, response = self.run_test(
            "Health Endpoint - Voice Configuration",
            "GET",
            "/api/health"
        )
        
        if not success:
            return False
            
        # Verify required fields are present
        required_fields = [
            "ok", "app", "tts_provider_ro", "elevenlabs_configured", "voice_settings"
        ]
        
        missing_fields = []
        for field in required_fields:
            if field not in response:
                missing_fields.append(field)
        
        if missing_fields:
            self.log_test(
                "Health Endpoint - Required Fields",
                False,
                {"missing_fields": missing_fields}
            )
            return False
        
        # Verify voice settings structure
        voice_settings = response.get("voice_settings", {})
        expected_voice_params = ["stability", "similarity_boost", "style", "use_speaker_boost"]
        missing_voice_params = []
        
        for param in expected_voice_params:
            if param not in voice_settings:
                missing_voice_params.append(param)
        
        if missing_voice_params:
            self.log_test(
                "Health Endpoint - Voice Settings Structure",
                False,
                {"missing_voice_params": missing_voice_params}
            )
            return False
        
        self.log_test(
            "Health Endpoint - Required Fields",
            True,
            {"voice_settings": voice_settings}
        )
        
        return True

    def test_voice_settings_endpoint(self) -> bool:
        """Test /api/voice-settings returns optimized parameters"""
        success, response = self.run_test(
            "Voice Settings Endpoint",
            "GET",
            "/api/voice-settings"
        )
        
        if not success:
            return False
        
        # Check if TTS provider is elevenlabs
        tts_provider = response.get("tts_provider", "").lower()
        if tts_provider != "elevenlabs":
            self.log_test(
                "Voice Settings - TTS Provider",
                False,
                {"expected": "elevenlabs", "actual": tts_provider}
            )
            return False
        
        # Verify optimized voice parameters
        expected_values = {
            "stability": 0.6,
            "similarity_boost": 0.75,
            "style": 0.4,
            "use_speaker_boost": True
        }
        
        validation_results = {}
        all_correct = True
        
        for param, expected_value in expected_values.items():
            actual_value = response.get(param)
            is_correct = actual_value == expected_value
            validation_results[param] = {
                "expected": expected_value,
                "actual": actual_value,
                "correct": is_correct
            }
            if not is_correct:
                all_correct = False
        
        self.log_test(
            "Voice Settings - Optimized Parameters",
            all_correct,
            {"parameter_validation": validation_results}
        )
        
        return all_correct

    def test_simulate_turn_romanian(self) -> bool:
        """Test /api/simulate-turn works with Romanian text"""
        romanian_test_data = {
            "session_id": f"test_session_{datetime.now().strftime('%H%M%S')}",
            "user_text": "Bună ziua! Cum mă puteți ajuta astăzi?"
        }
        
        success, response = self.run_test(
            "Simulate Turn - Romanian Text",
            "POST",
            "/api/simulate-turn",
            data=romanian_test_data
        )
        
        if not success:
            return False
        
        # Verify response structure
        required_fields = ["session_id", "language", "answer", "source"]
        missing_fields = []
        
        for field in required_fields:
            if field not in response:
                missing_fields.append(field)
        
        if missing_fields:
            self.log_test(
                "Simulate Turn - Response Structure",
                False,
                {"missing_fields": missing_fields}
            )
            return False
        
        # Verify language detection
        detected_language = response.get("language")
        if detected_language != "ro":
            self.log_test(
                "Simulate Turn - Language Detection",
                False,
                {"expected": "ro", "detected": detected_language}
            )
            return False
        
        # Verify answer is not empty
        answer = response.get("answer", "")
        if not answer or len(answer.strip()) == 0:
            self.log_test(
                "Simulate Turn - Answer Generation",
                False,
                {"answer_length": len(answer)}
            )
            return False
        
        self.log_test(
            "Simulate Turn - Romanian Processing",
            True,
            {
                "language_detected": detected_language,
                "answer_length": len(answer),
                "answer_preview": answer[:100] + "..." if len(answer) > 100 else answer
            }
        )
        
        return True

    def test_root_health_endpoint(self) -> bool:
        """Test root /health endpoint"""
        success, response = self.run_test(
            "Root Health Endpoint",
            "GET",
            "/health"
        )
        
        if not success:
            return False
        
        # Verify basic structure
        if not response.get("ok"):
            self.log_test(
                "Root Health - OK Status",
                False,
                {"ok_value": response.get("ok")}
            )
            return False
        
        return True

    def test_api_root(self) -> bool:
        """Test API root endpoint"""
        success, response = self.run_test(
            "API Root Endpoint",
            "GET",
            "/api/"
        )
        
        if not success:
            return False
        
        # Should return a message
        if "message" not in response:
            self.log_test(
                "API Root - Message Field",
                False,
                {"response": response}
            )
            return False
        
        return True

    def run_all_tests(self) -> Dict[str, Any]:
        """Run all tests and return summary"""
        print("🚀 Starting Voice Agent API Tests")
        print("=" * 50)
        print(f"Base URL: {self.base_url}")
        print()
        
        # Run individual tests
        test_methods = [
            self.test_root_health_endpoint,
            self.test_api_root,
            self.test_health_endpoint,
            self.test_voice_settings_endpoint,
            self.test_simulate_turn_romanian,
        ]
        
        for test_method in test_methods:
            try:
                test_method()
            except Exception as e:
                self.log_test(
                    f"EXCEPTION in {test_method.__name__}",
                    False,
                    {"exception": str(e), "exception_type": type(e).__name__}
                )
        
        # Print summary
        print("=" * 50)
        print("📊 TEST SUMMARY")
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%" if self.tests_run > 0 else "0%")
        
        # Categorize results
        passed_tests = [r for r in self.test_results if r["success"]]
        failed_tests = [r for r in self.test_results if not r["success"]]
        
        if failed_tests:
            print("\n❌ FAILED TESTS:")
            for test in failed_tests:
                print(f"  - {test['test_name']}")
                if test.get("details"):
                    for key, value in test["details"].items():
                        print(f"    {key}: {value}")
        
        if passed_tests:
            print(f"\n✅ PASSED TESTS ({len(passed_tests)}):")
            for test in passed_tests:
                print(f"  - {test['test_name']}")
        
        return {
            "total_tests": self.tests_run,
            "passed_tests": self.tests_passed,
            "failed_tests": self.tests_run - self.tests_passed,
            "success_rate": (self.tests_passed/self.tests_run*100) if self.tests_run > 0 else 0,
            "test_results": self.test_results,
            "passed_test_names": [t["test_name"] for t in passed_tests],
            "failed_test_names": [t["test_name"] for t in failed_tests]
        }

def main():
    """Main test execution"""
    tester = VoiceAgentAPITester()
    results = tester.run_all_tests()
    
    # Return appropriate exit code
    return 0 if results["failed_tests"] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())