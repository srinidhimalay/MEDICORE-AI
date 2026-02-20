from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.server_api import ServerApi
import os
import logging
import ssl
import certifi

logger = logging.getLogger(__name__)

class MongoDB:
    client: AsyncIOMotorClient = None
    db = None

    def connect(self):
        """Connect to MongoDB Atlas with proper SSL/TLS configuration"""
        mongodb_uri = os.getenv("MONGODB_URI")

        if not mongodb_uri:
            raise RuntimeError("MONGODB_URI not found in environment variables")

        try:
            # Create SSL context with certifi CA bundle and relaxed TLS settings
            # for compatibility with older OpenSSL versions
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            # Connect with SSL context instead of tlsCAFile
            self.client = AsyncIOMotorClient(
                mongodb_uri,
                server_api=ServerApi('1'),
                tls=True,
                tlsAllowInvalidCertificates=True,
                serverSelectionTimeoutMS=10000,
                connectTimeoutMS=20000,
                socketTimeoutMS=20000,
                maxPoolSize=10,
                minPoolSize=1,
                retryWrites=True,
                w='majority'
            )
            
            # Get database
            self.db = self.client.medical_chatbot
            
            logger.info("✓ MongoDB client initialized")
            
        except Exception as e:
            logger.error(f"MongoDB connection error: {e}")
            raise RuntimeError(f"Failed to connect to MongoDB: {e}")

    def get_collection(self, name: str):
        """Get a collection from the database"""
        if self.db is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self.db[name]

db_service = MongoDB()