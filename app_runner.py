import os
import logging
import secrets
import sys
from flask import Flask, render_template, request, jsonify, flash, session, redirect, send_file
from flask_login import LoginManager, current_user, login_required

# Try to use dotenv to load environment variables if available
try:
    from dotenv import load_dotenv
    # Try to load from .env file explicitly at this point
    if os.path.exists('.env'):
        load_dotenv(override=True)
        print("Loaded environment variables from .env file in app_runner.py")
except ImportError:
    print("python-dotenv not available. Environment variables must be set manually.")
except Exception as e:
    print(f"Error loading .env file: {e}")

# Import our JSON database and User class
from json_database import JSONDatabase
from google_auth import User

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if os.environ.get('DEBUG', 'False').lower() == 'true' else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configure OAuth token scope relaxation
# This allows mismatches between the requested and granted scopes
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

# Initialize the JSON database
db = JSONDatabase(data_dir=os.environ.get('DATA_DIR', 'data'))

def create_app():
    """Create and configure the Flask application"""
    app = Flask(__name__)
    
    # Check for Google OAuth credentials
    client_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')
    
    if client_id and client_secret:
        logger.info("Google OAuth credentials found in environment variables")
    else:
        # Try to reload from .env if they might have been missed
        try:
            from dotenv import load_dotenv
            if os.path.exists('.env'):
                load_dotenv(override=True)
                client_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
                client_secret = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')
                if client_id and client_secret:
                    logger.info("Loaded Google OAuth credentials from .env file in create_app()")
        except Exception as e:
            logger.error(f"Could not reload environment variables: {e}")
    
    # Set secret key from environment variable or use a random one
    app.secret_key = os.environ.get("SESSION_SECRET", None)
    if not app.secret_key:
        logger.warning("SESSION_SECRET environment variable not set. Using a generated secret key.")
        app.secret_key = secrets.token_hex(32)  # Generate a secure random key
        # Make sure we store it for future use
        os.environ["SESSION_SECRET"] = app.secret_key
    
    # Reload credentials one more time to ensure they're in the environment
    client_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')
    
    # Set configuration
    app.config.update(
        # Use secure cookies in production environments
        SESSION_COOKIE_SECURE=os.environ.get('FLASK_ENV', 'development') == 'production',
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        # Add Google OAuth configuration
        GOOGLE_OAUTH_CLIENT_ID=client_id,
        GOOGLE_OAUTH_CLIENT_SECRET=client_secret
    )
    
    # Check for Google OAuth configuration
    if not app.config.get('GOOGLE_OAUTH_CLIENT_ID') or not app.config.get('GOOGLE_OAUTH_CLIENT_SECRET'):
        logger.warning("Google OAuth credentials not properly configured. Authentication will not work.")
        if os.path.exists('.env'):
            with open('.env', 'r') as f:
                content = f.read()
                if 'GOOGLE_OAUTH_CLIENT_ID' in content and 'GOOGLE_OAUTH_CLIENT_SECRET' in content:
                    logger.error("Credentials found in .env file but not loaded into environment. Check file format.")
    else:
        logger.info("Google OAuth credentials configured successfully")
    
    # Set up Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'google_auth.login'
    
    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        user_data = db.get_user_by_id(int(user_id))
        if user_data:
            return User(user_data)
        return None
    
    # Import and register blueprints
    from google_auth import google_auth
    app.register_blueprint(google_auth)
    
    # Register all routes from app.py
    from app import register_routes
    register_routes(app)
    
    return app

if __name__ == '__main__':
    app = create_app()
    # Get port from environment variable or use 5000 as default
    port = int(os.environ.get('PORT', 5000))
    # Use debug mode based on environment variable
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    app.run(host="0.0.0.0", port=port, debug=debug)