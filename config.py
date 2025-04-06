import os

class Config:
    # Flask configuration
    SECRET_KEY = os.environ.get('SESSION_SECRET')
    DEBUG = True
    
    # Google API configuration
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
    
    # Application configuration
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500 MB max upload size
