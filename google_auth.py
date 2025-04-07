# Use this Flask blueprint for Google authentication

import json
import os
import logging
import sys

import requests
from flask import Blueprint, redirect, request, url_for, session, jsonify
from flask_login import login_user, logout_user, login_required
from oauthlib.oauth2 import WebApplicationClient

# NOTE: For production, we should use HTTPS for OAuth2
# Previously we set OAUTHLIB_INSECURE_TRANSPORT=1 for development, but now
# we're using proper HTTPS URIs that match Google Cloud Console configuration
# os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Import our JSON database
from json_database import JSONDatabase

logger = logging.getLogger(__name__)

# Initialize the JSON database
db = JSONDatabase()

# Get Google OAuth credentials from environment variables
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

# Log the credential status for debugging
if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    logger.error("Google OAuth credentials not found in environment variables. Authentication will not work.")
    # Try to re-load from .env file directly as a fallback
    try:
        from dotenv import load_dotenv
        if os.path.exists('.env'):
            logger.info("Attempting to reload credentials from .env file")
            load_dotenv(override=True)
            # Try again after reloading
            GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
            GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
            if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
                logger.info("Successfully loaded Google OAuth credentials from .env file")
            else:
                logger.error("Failed to load Google OAuth credentials from .env file")
    except ImportError:
        logger.error("Could not import dotenv to load environment variables")
    except Exception as e:
        logger.error(f"Error trying to load .env file: {e}")
else:
    logger.info("Google OAuth credentials found.")

# Get the redirect URI from environment if available
REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI')

# Log redirection information
if REDIRECT_URI:
    logger.info(f"Using configured redirect URI: {REDIRECT_URI}")
else:
    logger.info("No pre-configured redirect URI found. Will determine from request context.")

# Client configuration
client = None
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    client = WebApplicationClient(GOOGLE_CLIENT_ID)
    setup_message = "Google Auth is configured."
    if REDIRECT_URI:
        setup_message += f"\nMake sure to add this redirect URI to your Google Cloud Console: {REDIRECT_URI}"
    else:
        setup_message += "\nMake sure to add your domain's callback URL to your Google Cloud Console: https://YOUR_DOMAIN/google_login/callback"
    logger.info(setup_message)
else:
    logger.warning("Google OAuth credentials are not set. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in environment variables.")

google_auth = Blueprint("google_auth", __name__)

# Define the OAuth scopes needed
SCOPES = [
    'https://www.googleapis.com/auth/drive',  # Full Drive access to see all folders
    'https://www.googleapis.com/auth/drive.file',  # Access to files created by app
    # YouTube scopes added back in to enable YouTube uploads
    'https://www.googleapis.com/auth/youtube',  # Full access to YouTube on behalf of user
    'https://www.googleapis.com/auth/youtube.upload',  # Upload videos to YouTube
    'openid', 
    'email', 
    'profile'
]

# Create a User class compatible with Flask-Login
class User:
    def __init__(self, user_data):
        self.id = user_data['id']
        self.username = user_data['username']
        self.email = user_data['email']
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False

    def get_id(self):
        return str(self.id)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email
        }

@google_auth.route("/google_login")
def login():
    """Start the OAuth process for Google login"""
    if not client:
        return "Google OAuth credentials are not configured. Please set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET environment variables.", 500

    # Find out what URL to hit for Google login
    try:
        google_provider_cfg = requests.get(GOOGLE_DISCOVERY_URL).json()
        authorization_endpoint = google_provider_cfg["authorization_endpoint"]
    except Exception as e:
        logger.error(f"Error getting Google discovery information: {e}")
        return f"Error connecting to Google: {str(e)}", 500

    # Use a fixed redirect URI for Google Cloud Console configuration
    # Use the exact redirect URI registered in Google Cloud Console
    # This needs to match EXACTLY what's registered in your Google OAuth client

    # Use the redirect URI from environment variables if available (recommended for flexibility)
    redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI')
    
    # If no URI is configured in environment, use a fallback for this specific Replit instance
    if not redirect_uri:
        # Fallback to the hardcoded URI that works for this specific Replit project
        redirect_uri = "https://58de4355-ad39-416f-8a04-d0403694a826-00-23egjbjytsyo1.pike.replit.dev/google_login/callback"
        logger.info(f"Using fallback hardcoded Replit URI for auth: {redirect_uri}")
    else:
        logger.info(f"Using environment-configured redirect URI for auth: {redirect_uri}")
        
    # Important: The URI must match exactly what's registered in Google Cloud Console

    # Use library to construct the request for Google login and provide scopes
    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        redirect_uri=redirect_uri,
        scope=SCOPES,
        prompt="consent",  # Force to show login screen every time
        access_type="offline"  # Get refresh token
    )

    # Redirect to Google's OAuth page
    return redirect(request_uri)

@google_auth.route("/google_login/callback")
def callback():
    """Handle the Google OAuth callback"""
    # Log the full request details for debugging
    logger.info(f"Callback received. URL: {request.url}")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"Args: {dict(request.args)}")
    
    # Enhanced debugging
    try:
        logger.debug(f"Request method: {request.method}")
        logger.debug(f"Request remote addr: {request.remote_addr}")
        logger.debug(f"Request scheme: {request.scheme}")
        logger.debug(f"Request is_secure: {request.is_secure}")
        logger.debug(f"Request host: {request.host}")
        logger.debug(f"Full request: {request}")
    except Exception as e:
        logger.error(f"Error logging request details: {e}")

    if not client:
        logger.error("No OAuth client available. Check if credentials are configured.")
        return "Google OAuth credentials are not configured", 500

    # Get authorization code from Google
    code = request.args.get("code")
    if not code:
        error = request.args.get("error", "Missing code parameter in response.")
        logger.error(f"Error in Google callback: ({error})")
        return redirect("/?auth_error=" + error)

    # Find out what URL to hit to get tokens
    try:
        google_provider_cfg = requests.get(GOOGLE_DISCOVERY_URL).json()
        token_endpoint = google_provider_cfg["token_endpoint"]
    except Exception as e:
        logger.error(f"Error getting token endpoint: {e}")
        return f"Error connecting to Google token service: {str(e)}", 500

    # Use the same redirect URI as in the initial request for token generation
    # This is critical for OAuth to work correctly
    
    # Use the redirect URI from environment variables if available (recommended for flexibility)
    redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI')
    
    # If no URI is configured in environment, use a fallback for this specific Replit instance
    if not redirect_uri:
        # Fallback to the hardcoded URI that works for this specific Replit project
        redirect_uri = "https://58de4355-ad39-416f-8a04-d0403694a826-00-23egjbjytsyo1.pike.replit.dev/google_login/callback"
        logger.info(f"Using fallback hardcoded Replit URI for token exchange: {redirect_uri}")
    else:
        logger.info(f"Using environment-configured redirect URI for token exchange: {redirect_uri}")
        
    # Important: The URI must match exactly what's registered in Google Cloud Console

    # Prepare and send a request to get tokens
    try:
        # Always force using HTTPS on both the authorization_response and redirect_uri
        # This is critical because Google OAuth requires HTTPS
        
        # Get the authorization response URL
        authorization_response = request.url
        
        # Force HTTPS for the authorization response URL
        # This is necessary even if the actual request came through HTTP
        if authorization_response.startswith('http://'):
            authorization_response = authorization_response.replace('http://', 'https://')
            logger.info(f"Forced HTTPS in authorization_response: {authorization_response}")
            
        # Make sure the URI parts match what's registered in Google Cloud Console
        # Extract host, path, and query from the original URL, but force HTTPS scheme
        host = request.host
        path = request.path
        query = request.query_string.decode('utf-8') if hasattr(request.query_string, 'decode') else str(request.query_string)
        
        # Construct a new authorization response that exactly matches what Google expects
        # Use the same hostname as in the redirect_uri
        parsed_redirect = redirect_uri.split('//')[-1].split('/', 1)
        redirect_host = parsed_redirect[0]
        authorization_response = f"https://{redirect_host}/google_login/callback?{query}"
        
        logger.info(f"Fixed authorization_response to match redirect URI: {authorization_response}")
            
        token_url, headers, body = client.prepare_token_request(
            token_endpoint,
            authorization_response=authorization_response,
            redirect_url=redirect_uri,
            code=code
        )
        logger.debug(f"Token request prepared with token_url: {token_url}, headers: {headers}, body: {body}")
    except Exception as e:
        logger.error(f"Error preparing token request: {e}")
        logger.error(f"Request URL: {request.url}")
        logger.error(f"Redirect URI: {redirect_uri}")
        logger.error(f"Code: {code}")
        return f"Error preparing token request: {str(e)}", 500

    # Make sure we have valid credentials before using them
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        # This should never happen as we check earlier in the route
        return "Google OAuth credentials not properly configured", 500

    # Both credentials are not None, so we can use them
    try:
        token_response = requests.post(
            token_url,
            headers=headers,
            data=body,
            auth=(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET),
        )
        
        # Log response to help debug
        logger.info(f"Token response status: {token_response.status_code}")
        if token_response.status_code != 200:
            logger.error(f"Token response error: {token_response.text}")
            return f"Error from Google token endpoint: {token_response.text}", 500
        
        # Try to parse as JSON
        try:
            token_json = token_response.json()
            logger.debug(f"Token response JSON: {token_json}")
        except Exception as json_error:
            logger.error(f"Failed to parse token response as JSON: {json_error}")
            logger.error(f"Raw response: {token_response.text}")
            return "Invalid token response from Google", 500
            
        # Parse the tokens
        client.parse_request_body_response(json.dumps(token_json))
    except Exception as e:
        logger.error(f"Error getting token from Google: {e}")
        return f"Authentication error: {str(e)}", 500

    # Get user info from Google
    try:
        userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]
        uri, headers, body = client.add_token(userinfo_endpoint)
        userinfo_response = requests.get(uri, headers=headers, data=body)

        if not userinfo_response.ok:
            logger.error(f"Error getting user info: {userinfo_response.text}")
            return "Failed to get user info from Google", 500

        # Save credentials to session
        try:
            token_json = token_response.json()
            credentials = {
                'token': token_json['access_token'],
                'refresh_token': token_json.get('refresh_token'),
                'token_uri': 'https://oauth2.googleapis.com/token',
                'client_id': GOOGLE_CLIENT_ID,
                'client_secret': GOOGLE_CLIENT_SECRET,
                'scopes': SCOPES
            }
            session['credentials'] = json.dumps(credentials)
            logger.info("Saved credentials to session successfully")
        except Exception as e:
            logger.error(f"Error saving credentials to session: {e}")
            return f"Error processing authentication: {str(e)}", 500

        # Get user data
        user_data = userinfo_response.json()

        if not user_data.get("email_verified", False):
            return "User email not verified by Google", 400

        # Create or get user in our database
        email = user_data["email"]
        username = user_data.get("name", email.split('@')[0])

        # Check if user exists in our database
        existing_user = db.get_user_by_email(email)
        if existing_user:
            user = User(existing_user)
        else:
            # Create new user
            new_user_data = db.create_user(username, email)
            user = User(new_user_data)

        # Log in the user with Flask-Login
        login_user(user)

        # Send user back to homepage
        return redirect("/")
    except Exception as e:
        logger.error(f"Error in Google callback: {e}")
        return f"An error occurred during login: {str(e)}", 500

@google_auth.route("/logout")
@login_required
def logout():
    """Log out the user by clearing session data"""
    logout_user()
    session.clear()
    return redirect("/")