"""
Comprehensive API testing script for Medical Chatbot with Authentication.
Run this after starting the server: python main.py

Usage:
    python test_api_auth.py
"""

import requests
import json
import time
from typing import Dict, Any, Optional


BASE_URL = "http://localhost:8000"
TIMEOUT = 30

# Test user credentials
TEST_EMAIL = f"test_{int(time.time())}@example.com"
TEST_PASSWORD = "testpass123"
TEST_NAME = "Test User"


class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}")
    print(f"{text}")
    print(f"{'='*60}{Colors.ENDC}\n")


def print_success(text: str):
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_error(text: str):
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_info(text: str):
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")


def print_response(title: str, response: requests.Response):
    print(f"\n{Colors.BOLD}{title}{Colors.ENDC}")
    print("-" * 60)
    
    if response.status_code in [200, 201]:
        try:
            data = response.json()
            print(json.dumps(data, indent=2, default=str))
            print_success(f"Status: {response.status_code} OK")
        except json.JSONDecodeError:
            print(response.text)
            print_error("Invalid JSON response")
    else:
        print_error(f"Status: {response.status_code}")
        print(response.text)
    
    print("-" * 60)


def test_server_connection() -> bool:
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


def test_signup() -> Optional[Dict[str, Any]]:
    print_header("🔐 Testing User Signup")
    
    payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "name": TEST_NAME
    }
    
    print_info(f"Creating user: {TEST_EMAIL}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/signup",
            json=payload,
            timeout=TIMEOUT
        )
        
        print_response("Signup Response", response)
        
        if response.status_code == 201:
            data = response.json()
            if "access_token" in data:
                print_success("User registered successfully")
                return data
            else:
                print_error("Missing access_token in response")
                return None
        else:
            print_error(f"Signup failed with status {response.status_code}")
            return None
            
    except Exception as e:
        print_error(f"Signup failed: {str(e)}")
        return None


def test_login() -> Optional[Dict[str, Any]]:
    print_header("🔑 Testing User Login")
    
    payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    }
    
    print_info(f"Logging in as: {TEST_EMAIL}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json=payload,
            timeout=TIMEOUT
        )
        
        print_response("Login Response", response)
        
        if response.status_code == 200:
            data = response.json()
            if "access_token" in data:
                print_success("Login successful")
                return data
            else:
                print_error("Missing access_token in response")
                return None
        else:
            print_error(f"Login failed with status {response.status_code}")
            return None
            
    except Exception as e:
        print_error(f"Login failed: {str(e)}")
        return None


def test_create_new_chat(token: str) -> Optional[str]:
    print_header("💬 Testing New Chat Creation")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print_info("Creating new chat session...")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/chat/new",
            headers=headers,
            timeout=TIMEOUT
        )
        
        print_response("New Chat Response", response)
        
        if response.status_code == 200:
            data = response.json()
            if "chat_id" in data:
                print_success(f"Chat created with ID: {data['chat_id']}")
                return data['chat_id']
            else:
                print_error("Missing chat_id in response")
                return None
        else:
            print_error(f"Failed with status {response.status_code}")
            return None
            
    except Exception as e:
        print_error(f"Create chat failed: {str(e)}")
        return None


def test_chat_turn_1(token: str, chat_id: str) -> Optional[Dict[str, Any]]:
    print_header("💬 Testing Chat - Turn 1 (Initial Question)")
    
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "message": "I have a severe headache",
        "chat_id": chat_id,
        "awaiting_followup": False
    }
    
    print_info("Sending initial question...")
    print(f"Message: {payload['message']}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/chat",
            json=payload,
            headers=headers,
            timeout=TIMEOUT
        )
        
        print_response("Turn 1 Response", response)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("awaiting_followup") == True:
                print_success("Follow-up question generated")
                return data
            else:
                print_error("Expected awaiting_followup=True")
                return None
        else:
            print_error(f"Failed with status {response.status_code}")
            return None
            
    except Exception as e:
        print_error(f"Turn 1 failed: {str(e)}")
        return None


def test_chat_turn_2(token: str, chat_id: str) -> bool:
    print_header("💬 Testing Chat - Turn 2 (RAG Response)")
    
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "message": "Since this morning, about 6 hours ago",
        "chat_id": chat_id,
        "awaiting_followup": True
    }
    
    print_info("Answering follow-up question...")
    print(f"Message: {payload['message']}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/chat",
            json=payload,
            headers=headers,
            timeout=TIMEOUT
        )
        
        print_response("Turn 2 Response", response)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("awaiting_followup") == False:
                print_success("RAG response generated")
                if data.get("sources"):
                    print_success(f"Retrieved {len(data['sources'])} source chunks")
                return True
            else:
                print_error("Expected awaiting_followup=False")
                return False
        else:
            print_error(f"Failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print_error(f"Turn 2 failed: {str(e)}")
        return False


def test_get_chat_history(token: str) -> bool:
    print_header("📜 Testing Get Chat History")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print_info("Fetching chat history...")
    
    try:
        response = requests.get(
            f"{BASE_URL}/api/chat/history",
            headers=headers,
            timeout=TIMEOUT
        )
        
        print_response("Chat History Response", response)
        
        if response.status_code == 200:
            data = response.json()
            if "chats" in data:
                print_success(f"Found {len(data['chats'])} chat(s)")
                return True
            else:
                print_error("Missing 'chats' in response")
                return False
        else:
            print_error(f"Failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print_error(f"Get history failed: {str(e)}")
        return False


def test_get_chat_detail(token: str, chat_id: str) -> bool:
    print_header("📖 Testing Get Chat Detail")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print_info(f"Fetching chat detail for: {chat_id}")
    
    try:
        response = requests.get(
            f"{BASE_URL}/api/chat/{chat_id}",
            headers=headers,
            timeout=TIMEOUT
        )
        
        print_response("Chat Detail Response", response)
        
        if response.status_code == 200:
            data = response.json()
            if "messages" in data:
                print_success(f"Found {len(data['messages'])} message(s)")
                return True
            else:
                print_error("Missing 'messages' in response")
                return False
        else:
            print_error(f"Failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print_error(f"Get detail failed: {str(e)}")
        return False


def test_delete_chat(token: str, chat_id: str) -> bool:
    print_header("🗑️ Testing Delete Chat")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print_info(f"Deleting chat: {chat_id}")
    
    try:
        response = requests.delete(
            f"{BASE_URL}/api/chat/{chat_id}",
            headers=headers,
            timeout=TIMEOUT
        )
        
        print_response("Delete Response", response)
        
        if response.status_code == 200:
            print_success("Chat deleted successfully")
            return True
        else:
            print_error(f"Failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print_error(f"Delete failed: {str(e)}")
        return False


def test_logout(token: str) -> bool:
    print_header("🚪 Testing User Logout")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print_info("Logging out...")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/logout",
            headers=headers,
            timeout=TIMEOUT
        )
        
        print_response("Logout Response", response)
        
        if response.status_code == 200:
            print_success("Logout successful")
            return True
        else:
            print_error(f"Failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print_error(f"Logout failed: {str(e)}")
        return False


def run_all_tests():
    """Run complete test suite"""
    print(f"\n{Colors.BOLD}{'🧪'*30}")
    print("Medical Chatbot - Complete API Test Suite")
    print(f"{'🧪'*30}{Colors.ENDC}\n")
    
    # Check server
    if not test_server_connection():
        return
    
    time.sleep(0.5)
    
    results = {}
    token = None
    chat_id = None
    
    # Test signup
    signup_data = test_signup()
    results["Signup"] = signup_data is not None
    if signup_data:
        token = signup_data["access_token"]
    time.sleep(0.5)
    
    # Test login
    if token:
        login_data = test_login()
        results["Login"] = login_data is not None
        if login_data:
            token = login_data["access_token"]
        time.sleep(0.5)
    else:
        results["Login"] = False
    
    # Test create new chat
    if token:
        chat_id = test_create_new_chat(token)
        results["Create New Chat"] = chat_id is not None
        time.sleep(0.5)
    else:
        results["Create New Chat"] = False
    
    # Test chat turn 1
    if token and chat_id:
        turn1_data = test_chat_turn_1(token, chat_id)
        results["Chat Turn 1"] = turn1_data is not None
        time.sleep(1)
    else:
        results["Chat Turn 1"] = False
    
    # Test chat turn 2
    if token and chat_id:
        results["Chat Turn 2"] = test_chat_turn_2(token, chat_id)
        time.sleep(1)
    else:
        results["Chat Turn 2"] = False
    
    # Test get chat history
    if token:
        results["Get Chat History"] = test_get_chat_history(token)
        time.sleep(0.5)
    else:
        results["Get Chat History"] = False
    
    # Test get chat detail
    if token and chat_id:
        results["Get Chat Detail"] = test_get_chat_detail(token, chat_id)
        time.sleep(0.5)
    else:
        results["Get Chat Detail"] = False
    
    # Test delete chat
    if token and chat_id:
        results["Delete Chat"] = test_delete_chat(token, chat_id)
        time.sleep(0.5)
    else:
        results["Delete Chat"] = False
    
    # Test logout
    if token:
        results["Logout"] = test_logout(token)
        time.sleep(0.5)
    else:
        results["Logout"] = False
    
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
        print(f"\n{Colors.WARNING}{Colors.BOLD}⚠️ Some tests failed. Check the output above.{Colors.ENDC}")
    
    print()


if __name__ == "__main__":
    try:
        run_all_tests()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Tests interrupted by user{Colors.ENDC}\n")
    except Exception as e:
        print(f"\n\n{Colors.FAIL}Unexpected error: {str(e)}{Colors.ENDC}\n")