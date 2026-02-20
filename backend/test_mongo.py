"""
Standalone MongoDB Connection Test
Run this to verify your MongoDB Atlas connection is working

Usage:
    python test_mongo.py
"""

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.server_api import ServerApi
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


async def test_connection():
    """Test MongoDB connection with detailed diagnostics"""
    
    print("\n" + "="*60)
    print("MongoDB Connection Test")
    print("="*60 + "\n")
    
    # Get connection URI
    uri = os.getenv("MONGODB_URI")
    
    if not uri:
        print("❌ ERROR: MONGODB_URI not found in .env file")
        print("\nPlease ensure your .env file contains:")
        print("MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/database")
        return False
    
    # Mask password for display
    display_uri = uri
    if "@" in uri:
        parts = uri.split("@")
        user_part = parts[0].split("//")[1]
        if ":" in user_part:
            username = user_part.split(":")[0]
            display_uri = uri.replace(user_part, f"{username}:***")
    
    print(f"📡 Connection URI: {display_uri}\n")
    
    try:
        # Create client with same config as main app
        print("⏳ Connecting to MongoDB Atlas...")
        client = AsyncIOMotorClient(
            uri,
            server_api=ServerApi('1'),
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=10000
        )
        
        # Test 1: Ping
        print("⏳ Test 1: Ping database...")
        await client.admin.command('ping')
        print("✅ Ping successful!\n")
        
        # Test 2: List databases
        print("⏳ Test 2: Listing databases...")
        dbs = await client.list_database_names()
        print(f"✅ Found {len(dbs)} database(s): {', '.join(dbs)}\n")
        
        # Test 3: Access medical_chatbot database
        print("⏳ Test 3: Accessing medical_chatbot database...")
        db = client.medical_chatbot
        collections = await db.list_collection_names()
        
        if collections:
            print(f"✅ Found {len(collections)} collection(s): {', '.join(collections)}\n")
        else:
            print("✅ Database exists but has no collections yet (this is normal for new setup)\n")
        
        # Test 4: Try to insert and retrieve a test document
        print("⏳ Test 4: Testing write/read operations...")
        test_collection = db.connection_test
        
        # Insert test document
        test_doc = {"test": "connection", "timestamp": "now"}
        result = await test_collection.insert_one(test_doc)
        print(f"✅ Inserted test document with ID: {result.inserted_id}")
        
        # Read back
        found = await test_collection.find_one({"_id": result.inserted_id})
        if found:
            print("✅ Read back test document successfully")
        
        # Clean up
        await test_collection.delete_one({"_id": result.inserted_id})
        print("✅ Cleaned up test document\n")
        
        # Test 5: Check users and chats collections
        print("⏳ Test 5: Checking application collections...")
        users_collection = db.users
        chats_collection = db.chats
        
        user_count = await users_collection.count_documents({})
        chat_count = await chats_collection.count_documents({})
        
        print(f"✅ Users collection: {user_count} documents")
        print(f"✅ Chats collection: {chat_count} documents\n")
        
        # Close connection
        client.close()
        
        print("="*60)
        print("🎉 ALL TESTS PASSED!")
        print("="*60)
        print("\n✅ MongoDB is properly configured and working")
        print("✅ You can now run: python main.py")
        print("✅ Then test with: python test_api_auth.py\n")
        
        return True
        
    except asyncio.TimeoutError:
        print("\n" + "="*60)
        print("❌ CONNECTION TIMEOUT")
        print("="*60)
        print("\n🔍 Possible causes:")
        print("  1. IP address not whitelisted in MongoDB Atlas")
        print("     → Go to Network Access and add your IP or 0.0.0.0/0")
        print("  2. Cluster is paused")
        print("     → Go to Database and check if cluster is active")
        print("  3. Firewall blocking port 27017")
        print("     → Check your firewall/antivirus settings")
        print("  4. Internet connection issues")
        print("     → Try: ping ac-39mgwdi.ww3xmd9.mongodb.net\n")
        return False
        
    except Exception as e:
        print("\n" + "="*60)
        print("❌ CONNECTION FAILED")
        print("="*60)
        print(f"\n🔍 Error: {type(e).__name__}")
        print(f"📋 Details: {str(e)}\n")
        
        # Provide specific guidance based on error type
        error_str = str(e).lower()
        
        if "authentication failed" in error_str:
            print("🔧 Fix: Wrong username or password")
            print("  1. Go to MongoDB Atlas → Database Access")
            print("  2. Verify user: 1nt22cs124chetan_db_user")
            print("  3. Reset password if needed")
            print("  4. Update MONGODB_URI in .env file")
            
        elif "no replica set members" in error_str or "server selection" in error_str:
            print("🔧 Fix: Cannot reach MongoDB servers")
            print("  1. Check Network Access whitelist in Atlas")
            print("  2. Ensure cluster is not paused")
            print("  3. Verify internet connection")
            print("  4. Try different network (e.g., mobile hotspot)")
            
        elif "certificate" in error_str or "ssl" in error_str:
            print("🔧 Fix: SSL/TLS certificate issue")
            print("  1. Update certifi: pip install --upgrade certifi")
            print("  2. If on Windows: pip install python-certifi-win32")
            
        elif "invalid" in error_str and "connection string" in error_str:
            print("🔧 Fix: Invalid connection string format")
            print("  1. Ensure format is: mongodb+srv://user:pass@cluster/db")
            print("  2. Check for special characters in password (must be URL-encoded)")
            print("  3. Verify cluster address is correct")
        
        else:
            print("🔧 General troubleshooting:")
            print("  1. Check MongoDB Atlas status: https://status.cloud.mongodb.com/")
            print("  2. Verify all credentials are correct")
            print("  3. Try getting a fresh connection string from Atlas")
            print("  4. Check if cluster tier is active (not paused)")
        
        print()
        return False


def sync_test():
    """Wrapper to run async test"""
    try:
        return asyncio.run(test_connection())
    except KeyboardInterrupt:
        print("\n\n⚠️ Test interrupted by user\n")
        return False


if __name__ == "__main__":
    print("\n🧪 Starting MongoDB Connection Test...\n")
    print("Make sure you have:")
    print("  ✓ Updated .env file with correct MONGODB_URI")
    print("  ✓ Whitelisted your IP in MongoDB Atlas Network Access")
    print("  ✓ Installed required packages: pip install motor pymongo certifi\n")
    
    input("Press Enter to continue...")
    
    success = sync_test()
    
    if not success:
        print("\n⚠️ Connection test failed. Please fix the issues above and try again.\n")
        exit(1)
    else:
        print("✅ Connection test completed successfully!\n")
        exit(0)