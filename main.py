import os
import logging
import sys
from dotenv import load_dotenv
from app_runner import create_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file if it exists
try:
    # Try to load from .env file
    if os.path.exists('.env'):
        # Force loading from .env file, overriding existing environment variables
        load_dotenv(override=True)
        logger.info("Loaded environment variables from .env file")
        
        # Log the credentials status (safely)
        client_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
        client_secret = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')
        
        if client_id and client_secret:
            # Mask the credentials for security when logging
            masked_id = client_id[:10] + "..." if len(client_id) > 10 else "***"
            masked_secret = "***" + client_secret[-4:] if len(client_secret) > 4 else "***"
            logger.info(f"Google OAuth credentials found: ID={masked_id}, Secret={masked_secret}")
        else:
            logger.warning("Google OAuth credentials not found in .env file")
    else:
        logger.info("No .env file found, using system environment variables")
except Exception as e:
    logger.error(f"Error loading .env file: {e}")

# Ensure we have minimum required environment variables
if not os.environ.get('GOOGLE_OAUTH_CLIENT_ID') or not os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET'):
    logger.warning("Google OAuth credentials not found in environment variables. Authentication will not work properly.")
    # Print to stderr for more visibility
    print("ERROR: Google OAuth credentials not found. Check your .env file.", file=sys.stderr)

# For local development without HTTPS, this can be enabled
if os.environ.get('FLASK_ENV') == 'development' and os.environ.get('ALLOW_INSECURE_OAUTH') == 'True':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    logger.warning("Insecure OAuth transport enabled for development. Do not use in production!")

# Create the Flask application
app = create_app()

# Get port from environment variable (for Heroku/etc.) or use 5000 as default
port = int(os.environ.get('PORT', 5000))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port, debug=os.environ.get('DEBUG', 'False').lower() == 'true')