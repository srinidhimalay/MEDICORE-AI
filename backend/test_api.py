"""
Comprehensive API testing script for Medical Chatbot.
Run this after starting the server: python main.py

Usage:
    python test_api.py
"""

import requests
import json
import time
from typing import Dict, Any


BASE_URL = "http://localhost:8000"
TIMEOUT = 30  # seconds


class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    """Print formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}")
    print(f"{text}")
    print(f"{'='*60}{Colors.ENDC}\n")


def print_success(text: str):
    """Print success message"""
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_error(text: str):
    """Print error message"""
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_info(text: str):
    """Print info message"""
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")


def print_response(title: str, response: requests.Response):
    """Pretty print API response"""
    print(f"\n{Colors.BOLD}{title}{Colors.ENDC}")
    print("-" * 60)
    
    if response.status_code == 200:
        try:
            data = response.json()
            print(json.dumps(data, indent=2))
            print_success(f"Status: {response.status_code} OK")
        except json.JSONDecodeError:
            print(response.text)
            print_error("Invalid JSON response")
    else:
        print_error(f"Status: {response.status_code}")
        print(response.text)
    
    print("-" * 60)


def test_server_connection() -> bool:
    """Test if server is running"""
    print_header("🔌 Testing Server Connection")
    
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        if response.status_code == 200:
            print_success("Server is running")
            print_info(f"URL: {BASE_URL}")
            return True
        else:
            print_error(f"Server responded with status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print_error("Cannot connect to server")
        print_info("Please start the server: python main.py")
        return False
    except Exception as e:
        print_error(f"Connection error: {str(e)}")
        return False


def test_health() -> bool:
    """Test health endpoint"""
    print_header("🏥 Testing Health Endpoint")
    
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        print_response("Health Check Response", response)
        return response.status_code == 200
    except Exception as e:
        print_error(f"Health check failed: {str(e)}")
        return False


def test_chat_turn_1() -> Dict[str, Any]:
    """Test chat turn 1 (initial question)"""
    print_header("💬 Testing Chat - Turn 1 (Initial Question)")
    
    payload = {
        "message": "I have a severe headache",
        "chat_history": [],
        "awaiting_followup": False
    }
    
    print_info("Sending initial question...")
    print(f"Message: {payload['message']}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/chat",
            json=payload,
            timeout=TIMEOUT
        )
        
        print_response("Turn 1 Response", response)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("awaiting_followup") == True:
                print_success("Follow-up question generated successfully")
                return data
            else:
                print_error("Expected awaiting_followup=True")
                return None
        else:
            print_error(f"Request failed with status {response.status_code}")
            return None
            
    except Exception as e:
        print_error(f"Turn 1 failed: {str(e)}")
        return None


def test_chat_turn_2(turn1_data: Dict[str, Any]) -> bool:
    """Test chat turn 2 (answer follow-up)"""
    print_header("💬 Testing Chat - Turn 2 (RAG Response)")
    
    if not turn1_data:
        print_error("Turn 1 data not available, skipping Turn 2")
        return False
    
    payload = {
        "message": "Since this morning, about 6 hours ago",
        "chat_history": [
            {"role": "user", "content": "I have a severe headache"},
            {"role": "assistant", "content": turn1_data["response"]}
        ],
        "awaiting_followup": True
    }
    
    print_info("Answering follow-up question...")
    print(f"Message: {payload['message']}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/chat",
            json=payload,
            timeout=TIMEOUT
        )
        
        print_response("Turn 2 Response", response)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("awaiting_followup") == False:
                print_success("RAG response generated successfully")
                if data.get("sources"):
                    print_success(f"Retrieved {len(data['sources'])} source chunks")
                return True
            else:
                print_error("Expected awaiting_followup=False")
                return False
        else:
            print_error(f"Request failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print_error(f"Turn 2 failed: {str(e)}")
        return False


def test_simplify() -> bool:
    """Test text simplification"""
    print_header("🔄 Testing Text Simplification")
    
    complex_text = """**Overview**
Cephalgia, commonly referred to as headache, is a complex neurological 
condition characterized by pain or discomfort in the cranial region. 
The pathophysiology involves various mechanisms including vascular changes, 
muscular tension, inflammatory processes, and neural sensitization."""
    
    payload = {
        "chat_history": [
            {"role": "assistant", "content": complex_text}
        ]
    }
    
    print_info("Simplifying complex medical text...")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/simplify",
            json=payload,
            timeout=TIMEOUT
        )
        
        print_response("Simplified Response", response)
        
        if response.status_code == 200:
            data = response.json()
            if "simplified" in data:
                print_success("Text simplified successfully")
                return True
            else:
                print_error("Missing 'simplified' field in response")
                return False
        else:
            print_error(f"Request failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print_error(f"Simplification failed: {str(e)}")
        return False


def test_emergency_detection() -> bool:
    """Test emergency keyword detection"""
    print_header("🚨 Testing Emergency Detection")
    
    payload = {
        "message": "I'm having severe chest pain and can't breathe",
        "chat_history": [],
        "awaiting_followup": False
    }
    
    print_info("Sending message with emergency keywords...")
    print(f"Message: {payload['message']}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/chat",
            json=payload,
            timeout=TIMEOUT
        )
        
        print_response("Emergency Response", response)
        
        if response.status_code == 200:
            data = response.json()
            if "EMERGENCY" in data["response"].upper():
                print_success("Emergency detected correctly")
                return True
            else:
                print_error("Emergency keywords not detected")
                return False
        else:
            print_error(f"Request failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print_error(f"Emergency detection test failed: {str(e)}")
        return False


def test_input_validation() -> bool:
    """Test input validation"""
    print_header("✅ Testing Input Validation")
    
    test_cases = [
        {
            "name": "Empty message",
            "payload": {"message": "", "chat_history": [], "awaiting_followup": False},
            "should_fail": True
        },
        {
            "name": "Too short message",
            "payload": {"message": "hi", "chat_history": [], "awaiting_followup": False},
            "should_fail": True
        },
        {
            "name": "Valid message",
            "payload": {"message": "I have a fever", "chat_history": [], "awaiting_followup": False},
            "should_fail": False
        }
    ]
    
    all_passed = True
    
    for test_case in test_cases:
        print_info(f"Testing: {test_case['name']}")
        
        try:
            response = requests.post(
                f"{BASE_URL}/api/chat",
                json=test_case["payload"],
                timeout=TIMEOUT
            )
            
            if test_case["should_fail"]:
                # Expecting validation to catch this
                if response.status_code in [200, 400, 422]:
                    print_success(f"✓ {test_case['name']}: Handled correctly")
                else:
                    print_error(f"✗ {test_case['name']}: Unexpected status {response.status_code}")
                    all_passed = False
            else:
                if response.status_code == 200:
                    print_success(f"✓ {test_case['name']}: Passed")
                else:
                    print_error(f"✗ {test_case['name']}: Should have passed")
                    all_passed = False
                    
        except Exception as e:
            print_error(f"✗ {test_case['name']}: {str(e)}")
            all_passed = False
    
    return all_passed


def run_all_tests():
    """Run complete test suite"""
    print(f"\n{Colors.BOLD}{'🧪'*30}")
    print("Medical Chatbot - API Test Suite")
    print(f"{'🧪'*30}{Colors.ENDC}\n")
    
    # Check server connection first
    if not test_server_connection():
        return
    
    time.sleep(0.5)
    
    # Run tests
    results = {}
    
    # Health check
    results["Health Check"] = test_health()
    time.sleep(0.5)
    
    # Chat flow
    turn1_data = test_chat_turn_1()
    results["Chat Turn 1"] = turn1_data is not None
    time.sleep(1)
    
    if turn1_data:
        results["Chat Turn 2"] = test_chat_turn_2(turn1_data)
        time.sleep(1)
    else:
        results["Chat Turn 2"] = False
    
    # Simplification
    results["Simplification"] = test_simplify()
    time.sleep(0.5)
    
    # Emergency detection
    results["Emergency Detection"] = test_emergency_detection()
    time.sleep(0.5)
    
    # Input validation
    results["Input Validation"] = test_input_validation()
    
    # Print summary
    print_header("📊 Test Summary")
    
    for test_name, passed in results.items():
        status = f"{Colors.OKGREEN}✅ PASSED{Colors.ENDC}" if passed else f"{Colors.FAIL}❌ FAILED{Colors.ENDC}"
        print(f"{test_name:.<40} {status}")
    
    total = len(results)
    passed = sum(results.values())
    percentage = (passed / total * 100) if total > 0 else 0
    
    print(f"\n{Colors.BOLD}Total: {passed}/{total} tests passed ({percentage:.1f}%){Colors.ENDC}")
    
    if passed == total:
        print(f"\n{Colors.OKGREEN}{Colors.BOLD}🎉 All tests passed! API is working correctly.{Colors.ENDC}")
    else:
        print(f"\n{Colors.WARNING}{Colors.BOLD}⚠️  Some tests failed. Check the output above.{Colors.ENDC}")
    
    print()


if __name__ == "__main__":
    try:
        run_all_tests()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Tests interrupted by user{Colors.ENDC}\n")
    except Exception as e:
        print(f"\n\n{Colors.FAIL}Unexpected error: {str(e)}{Colors.ENDC}\n")