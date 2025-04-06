import os
import logging
import tempfile
import json
import time
import subprocess
from datetime import datetime
from urllib.parse import urlparse, parse_qs

# Import utilities and database
from json_database import JSONDatabase
from utils import format_duration, is_valid_youtube_url, safe_filename, generate_temp_filename

from flask import Flask, render_template, request, jsonify, flash, session, redirect, send_file
# Handle YouTube downloads without cookies for now
import yt_dlp
from yt_dlp.utils import YoutubeDLError
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
import requests
from flask_login import LoginManager, current_user, login_required

# Initialize the JSON database
db = JSONDatabase()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Temporary directory for storing downloads
temp_dir = tempfile.gettempdir()

# Google Drive API scopes
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# Create a mock User class for Flask-Login compatibility
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

# User loader for Flask-Login
def load_user(user_id):
    user_data = db.get_user_by_id(int(user_id))
    if user_data:
        return User(user_data)
    return None
    
def get_authenticated_service():
    """Build and return a Drive service object"""
    try:
        credentials_json = session.get('credentials')
        if not credentials_json:
            logger.warning("No credentials in session")
            return None
        
        # Load credentials from session
        credentials_data = json.loads(credentials_json)
        credentials = Credentials.from_authorized_user_info(credentials_data)
        
        # If credentials are expired and we have a refresh token, refresh them
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            
            # Save the updated credentials back to the session
            updated_creds = {
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes
            }
            session['credentials'] = json.dumps(updated_creds)
        
        return build('drive', 'v3', credentials=credentials)
    except Exception as e:
        logger.error(f"Error getting authenticated service: {e}")
        return None

def register_routes(app):
    """Register all routes with the Flask app"""
    
    # Define route functions inside this function to avoid global scope
    
    @app.route('/debug')
    def debug_info():
        """Display debug information about the application environment"""
        import os
        import platform
        import sys
        
        # Gather environment info
        env_info = {
            'PLATFORM': platform.platform(),
            'PYTHON_VERSION': sys.version,
            'APPLICATION_HOST': request.host if request else 'Not available',
            'FLASK_ENV': os.environ.get('FLASK_ENV', 'Not set'),
            'DEBUG': os.environ.get('DEBUG', 'Not set'),
            'GOOGLE_OAUTH_CLIENT_ID': 'Set' if os.environ.get('GOOGLE_OAUTH_CLIENT_ID') else 'Not set',
            'GOOGLE_OAUTH_CLIENT_SECRET': 'Set' if os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET') else 'Not set',
            'GOOGLE_REDIRECT_URI': os.environ.get('GOOGLE_REDIRECT_URI', 'Not set'),
            'SESSION_SECRET': 'Set' if app.secret_key else 'Not set',
            'DATABASE_URL': 'Set' if os.environ.get('DATABASE_URL') else 'Not set',
            'ALLOW_INSECURE_OAUTH': os.environ.get('ALLOW_INSECURE_OAUTH', 'Not set'),
            'DATA_DIR': os.environ.get('DATA_DIR', 'Not set')
        }
        
        # Check for .env file status
        dotenv_status = "Not checked"
        try:
            if os.path.exists('.env'):
                dotenv_status = ".env file exists"
                # Try to check if expected variables are in the environment
                with open('.env', 'r') as f:
                    env_content = f.read()
                    env_vars_in_file = []
                    for line in env_content.splitlines():
                        if line.strip() and not line.strip().startswith('#'):
                            if '=' in line:
                                var_name = line.split('=')[0].strip()
                                env_vars_in_file.append(var_name)
                    
                    # Check if these variables are actually in the environment
                    loaded_vars = [var for var in env_vars_in_file if os.environ.get(var) is not None]
                    dotenv_status = f".env file exists with {len(env_vars_in_file)} variables. {len(loaded_vars)}/{len(env_vars_in_file)} variables loaded."
            else:
                dotenv_status = "No .env file found"
        except Exception as e:
            dotenv_status = f"Error checking .env: {str(e)}"
        
        # Get OAuth redirect URI from environment or construct from request
        redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI')
        if not redirect_uri:
            # Default to HTTPS for OAuth
            scheme = 'https'
            redirect_uri = f"{scheme}://{request.host}/google_login/callback"
        
        return f"""
        <h1>Debug Information</h1>
        <h2>Environment Information</h2>
        <pre>{env_info}</pre>
        <h2>.env File Status</h2>
        <pre>{dotenv_status}</pre>
        <h2>OAuth Redirect URL</h2>
        <p>Make sure to add this URL to your Google Cloud Console as an authorized redirect URI:</p>
        <code>{redirect_uri}</code>
        <h2>OAuth Configuration Status</h2>
        <p>Google OAuth Client ID: {'Configured' if os.environ.get('GOOGLE_OAUTH_CLIENT_ID') else 'Not configured'}</p>
        <p>Google OAuth Client Secret: {'Configured' if os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET') else 'Not configured'}</p>
        <p>Insecure OAuth Transport: {'Enabled' if os.environ.get('OAUTHLIB_INSECURE_TRANSPORT') == '1' else 'Disabled'}</p>
        <p><a href="/">Back to Home</a></p>
        """
        
    @app.route('/')
    def index():
        """Render the main page with options"""
        return render_template('index.html')

    @app.route('/download')
    def download_page():
        """Render the download page"""
        return render_template('download.html')

    @app.route('/metadata')
    def metadata_page():
        """Render the metadata extraction page"""
        return render_template('metadata.html')

    @app.route('/get_metadata', methods=['POST'])
    def get_metadata():
        """Extract metadata from YouTube URL"""
        try:
            data = request.get_json()
            url = data.get('url', '')

            if not is_valid_youtube_url(url):
                return jsonify({'error': 'Invalid YouTube URL'}), 400

            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'youtube_include_dash_manifest': False,  # Disable DASH manifest extraction for cookies fix
                'no_check_certificate': True,  # Avoid certificate issues
                'nocheckcertificate': True  # Legacy option for ensuring no certificate check
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            return jsonify({
                'title': info.get('title', 'Unknown title'),
                'description': info.get('description', 'No description available'),
                'channel': info.get('uploader', 'Unknown channel'),
                'duration': format_duration(info.get('duration', 0)),
                'tags': info.get('tags', [])
            })
        except Exception as e:
            logger.error(f"Error extracting metadata: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/history_page')
    def history_page():
        """Render the history page"""
        return render_template('history.html')

    @app.route('/auth')
    def auth():
        """Start the OAuth flow - redirects to the Google Auth blueprint"""
        return redirect('/google_login')

    @app.route('/get_video_info', methods=['POST'])
    def get_video_info():
        """Get video information from YouTube URL"""
        try:
            data = request.get_json()
            url = data.get('url', '')

            # Validate YouTube URL
            parsed_url = urlparse(url)
            if 'youtube.com' not in parsed_url.netloc and 'youtu.be' not in parsed_url.netloc:
                return jsonify({'error': 'Invalid YouTube URL'}), 400

            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'youtube_include_dash_manifest': False,  # Disable DASH manifest for cookies fix
                'no_check_certificate': True,  # Avoid certificate issues
                'nocheckcertificate': True,  # Legacy option
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android'],
                    }
                },
                'geo_bypass': True,
                'force_ipv4': True
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            return jsonify({
                'title': info.get('title', 'Unknown title'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'uploader': info.get('uploader', 'Unknown uploader'),
            })
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/download', methods=['POST'])
    def download_video():
        """Download video from YouTube URL"""
        data = request.get_json()
        logger.info(f"Download data received: {data}")

        url = data.get('url', '')

        # Create a unique filename
        timestamp = int(time.time())
        temp_file = os.path.join(temp_dir, f"yt_video_{timestamp}")
        temp_file_mp4 = temp_file + '.mp4'  # Default to mp4 for backup methods
        logger.info(f"Temp file path: {temp_file}")

        # For testing, use the simplest command possible
        try:
            subprocess.run(['pip', 'list'], capture_output=True, text=True)

            # Try best format under 720p with increased file size limit
            cmd = f"yt-dlp -f 'bv*[height<=720]+ba/b[height<=720] / wv*+ba/w' --no-check-certificate --no-warnings --no-cache-dir --no-playlist --max-filesize 1536M -o '{temp_file_mp4}' '{url}'"
            logger.info(f"Running direct low-quality download: {cmd}")
            process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                stdout, stderr = process.communicate(timeout=300)  # 5 minute timeout for downloads
                if process.returncode != 0:
                    # First attempt failed, try with generic method
                    logger.warning(f"Low quality download failed: {stderr.decode()}")
                    
                    # Try generic download without YouTube extractor
                    fallback_cmd = f"yt-dlp --force-generic-extractor --no-check-certificate --no-cache-dir --no-playlist --max-filesize 50M -o '{temp_file_mp4}' '{url}'"
                    logger.info(f"Running generic download: {fallback_cmd}")
                    
                    fallback_process = subprocess.Popen(fallback_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    fallback_stdout, fallback_stderr = fallback_process.communicate(timeout=120)
                    
                    # If still failed, try with curl directly
                    if fallback_process.returncode != 0:
                        logger.warning(f"Generic download failed: {fallback_stderr.decode()}")
                        
                        # Use youtube-dl as final attempt
                        last_cmd = f"youtube-dl -f '18/17/36/best[height<=360]' --no-check-certificate --no-warnings --no-playlist -o '{temp_file_mp4}' '{url}'"
                        logger.info(f"Running youtube-dl attempt: {last_cmd}")
                        
                        last_process = subprocess.Popen(last_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        last_stdout, last_stderr = last_process.communicate(timeout=120)
                        
                        if last_process.returncode != 0:
                            raise Exception(f"All download methods failed: {last_stderr.decode()}")
            except subprocess.TimeoutExpired:
                if 'process' in locals():
                    process.kill()
                logger.error("Download timed out")
                
                # Continue with info extraction from URL, even if download failed
                try:
                    # Extract basic info directly from URL
                    youtube_id = url.split('?')[0].split('/')[-1]
                    # Create basic metadata
                    video_info = {
                        'youtube_id': youtube_id,
                        'title': f"Video {youtube_id}",
                        'duration': 0,
                        'thumbnail_url': f"https://i.ytimg.com/vi/{youtube_id}/hqdefault.jpg",
                        'uploader': 'Unknown (timeout)',
                        'filename': temp_file_mp4
                    }
                    
                    # Create an empty file so subsequent processing won't fail
                    with open(temp_file_mp4, 'wb') as f:
                        f.write(b'Error downloading video - timed out')
                    
                    return jsonify({'error': 'Download timed out'}), 408
                except Exception as ex:
                    logger.error(f"Error in timeout handler: {ex}")
                    raise Exception("Download timed out and recovery failed")

            if os.path.exists(temp_file_mp4):
                logger.info(f"File downloaded successfully: {temp_file_mp4}")

                # Get metadata with enhanced options
                try:
                    ydl_opts = {
                        'quiet': True, 
                        'skip_download': True,
                        'extractor_args': {
                            'youtube': {
                                'player_client': ['android'],
                            }
                        },
                        'geo_bypass': True,
                        'force_ipv4': True
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)

                    video_info = {
                        'youtube_id': info.get('id', ''),
                        'title': info.get('title', 'Unknown'),
                        'duration': info.get('duration', 0),
                        'thumbnail_url': info.get('thumbnail', ''),
                        'uploader': info.get('uploader', 'Unknown uploader'),
                        'filename': temp_file_mp4
                    }
                except Exception as e:
                    logger.warning(f"Could not get metadata: {e}")
                    # Fallback metadata
                    video_info = {
                        'youtube_id': url.split('v=')[-1] if 'v=' in url else url.split('/')[-1],
                        'title': os.path.basename(temp_file_mp4),
                        'duration': 0,
                        'thumbnail_url': '',
                        'uploader': 'Unknown',
                        'filename': temp_file_mp4
                    }

                return process_downloaded_video(url, video_info)

        except Exception as e:
            logger.error(f"Download error: {e}")

            # Last attempt - basic pytube
            try:
                logger.info("Trying basic pytube...")
                from pytube import YouTube
                yt = YouTube(url)
                highest_res_stream = yt.streams.get_highest_resolution()
                if highest_res_stream:
                    download_path = highest_res_stream.download(output_path=temp_dir, filename=f"yt_video_{timestamp}.mp4")
                    logger.info(f"Downloaded with pytube: {download_path}")

                    if os.path.exists(download_path):
                        video_info = {
                            'youtube_id': yt.video_id,
                            'title': yt.title,
                            'duration': yt.length,
                            'thumbnail_url': yt.thumbnail_url,
                            'uploader': yt.author,
                            'filename': download_path
                        }
                        return process_downloaded_video(url, video_info)
            except Exception as pytube_error:
                logger.error(f"Basic pytube error: {pytube_error}")

        # If all methods fail
        return jsonify({'error': 'All download methods failed'}), 500

    def process_downloaded_video(url, video_info):
        """Process a successfully downloaded video and create database entry"""
        try:
            filename = video_info['filename']
            # Get file size
            file_size = os.path.getsize(filename)
            logger.info(f"File size: {file_size} bytes")

            # Prepare video data for JSON database
            video_data = {
                'youtube_id': video_info['youtube_id'],
                'title': video_info['title'],
                'url': url,
                'duration': video_info['duration'],
                'thumbnail_url': video_info['thumbnail_url'],
                'uploader': video_info['uploader'],
                'file_size': file_size,
                'download_success': True,
                'uploaded_to_drive': False,
                'drive_file_id': None,
                'drive_folder_id': None,
                'uploaded_to_youtube': False,
                'youtube_upload_id': None,
                'user_id': current_user.id if hasattr(current_user, 'id') and not current_user.is_anonymous else None
            }

            # Create video record in JSON database
            video = db.create_video(video_data)
            logger.info(f"Video record created with ID: {video['id']}")

            # Add video ID to response for later reference
            response_data = {
                'status': 'success',
                'message': 'Video downloaded successfully',
                'filename': filename,
                'title': video_info['title'],
                'video_id': video['id']
            }
            logger.info(f"Sending response with data: {response_data}")
            return jsonify(response_data)
        except Exception as e:
            logger.error(f"Error processing downloaded video: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/upload_to_drive', methods=['POST'])
    def upload_to_drive():
        """Upload video to Google Drive"""
        try:
            data = request.get_json()
            filename = data.get('filename', '')
            folder_id = data.get('folder_id', None)
            video_id = data.get('video_id', None)

            if not os.path.exists(filename):
                return jsonify({'error': 'File not found'}), 404

            drive_service = get_authenticated_service()
            if not drive_service:
                return jsonify({'error': 'Not authenticated with Google Drive'}), 401

            # Create file metadata
            file_metadata = {
                'name': os.path.basename(filename),
            }

            if folder_id:
                file_metadata['parents'] = [folder_id]

            # Upload file with larger chunk size for faster uploads (50MB)
            chunk_size = 52428800  # 50MB chunks (default is 1MB)
            media = MediaFileUpload(
                filename, 
                resumable=True,
                chunksize=chunk_size
            )

            file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()

            # Update database record if video_id was provided
            if video_id:
                video = db.get_video_by_id(int(video_id))
                if video:
                    db.update_video(int(video_id), {
                        'uploaded_to_drive': True,
                        'drive_file_id': file.get('id'),
                        'drive_folder_id': folder_id
                    })

            return jsonify({
                'status': 'success',
                'message': 'Video uploaded to Google Drive',
                'file_id': file.get('id')
            })
        except Exception as e:
            logger.error(f"Upload error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/get_drive_folders', methods=['GET'])
    def get_drive_folders():
        """Get list of Google Drive folders"""
        try:
            drive_service = get_authenticated_service()
            if not drive_service:
                return jsonify({'error': 'Not authenticated with Google Drive'}), 401

            # Query for folders only
            query = "mimeType='application/vnd.google-apps.folder' and trashed=false"
            fields = "files(id, name)"
            
            results = drive_service.files().list(
                q=query,
                fields=fields
            ).execute()
            
            folders = results.get('files', [])
            
            return jsonify({
                'status': 'success',
                'folders': folders
            })
        except Exception as e:
            logger.error(f"Error listing folders: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/upload_to_yt', methods=['POST'])
    def upload_to_yt():
        """Upload video to YouTube with original metadata"""
        try:
            # Check if user is logged in 
            if not hasattr(current_user, 'id') or current_user.is_anonymous:
                return jsonify({'error': 'You must be logged in to upload to YouTube'}), 401
                
            # Extract request data
            request_data = request.get_json()
            if not request_data:
                return jsonify({'error': 'Invalid request data'}), 400
                
            filename = request_data.get('filename')
            video_id = request_data.get('video_id')
            privacy_status = request_data.get('privacy_status', 'private')
            
            if not filename or not video_id:
                return jsonify({'error': 'Missing required parameters (filename or video_id)'}), 400
                
            # Get video information from database
            video = db.get_video_by_id(int(video_id))
            if not video:
                return jsonify({'error': 'Video not found in database'}), 404
                
            # Verify the file exists
            file_path = filename
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return jsonify({'error': 'Video file not found'}), 404
                
            # Get an authenticated YouTube service
            try:
                # Check if we have YouTube scope in the credentials
                if 'credentials' not in session:
                    logger.error("No credentials in session")
                    return jsonify({
                        'error': 'You need to authorize YouTube access',
                        'action_required': 'reauth'
                    }), 401
                
                # Check for YouTube scope in stored credentials
                credentials_data = json.loads(session['credentials'])
                scopes = credentials_data.get('scopes', [])
                
                logger.info(f"Available scopes for upload: {scopes}")
                
                # Check if we have YouTube upload scope
                youtube_scopes = ['https://www.googleapis.com/auth/youtube',
                                 'https://www.googleapis.com/auth/youtube.upload']
                has_youtube_scope = any(scope in scopes for scope in youtube_scopes)
                
                if not has_youtube_scope:
                    logger.warning("Missing YouTube upload scope")
                    # Return a helpful error to guide user to re-authenticate
                    return jsonify({
                        'error': 'YouTube upload permission not granted. Please log out and log back in.',
                        'action_required': 'reauth'
                    }), 403
                    
                # Create YouTube service with credentials
                credentials_dict = {
                    'token': credentials_data.get('token'),
                    'refresh_token': credentials_data.get('refresh_token'),
                    'token_uri': credentials_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
                    'client_id': credentials_data.get('client_id'),
                    'client_secret': credentials_data.get('client_secret'),
                    'scopes': scopes
                }
                
                credentials = Credentials.from_authorized_user_info(credentials_dict)
                youtube = build('youtube', 'v3', credentials=credentials)
                
                # Prepare video metadata from the original video using stored information
                title = video.get('title', 'Uploaded Video')
                
                # Get more detailed metadata directly from YouTube using yt-dlp
                # For shorts, we need to convert shorts URL to standard video URL
                video_url = video.get('url', '')
                youtube_id = None
                
                # Extract YouTube ID from URL
                try:
                    if 'youtube.com/shorts/' in video_url:
                        youtube_id = video_url.split('shorts/')[1].split('?')[0]
                    elif 'youtube.com/watch?v=' in video_url:
                        youtube_id = video_url.split('watch?v=')[1].split('&')[0]
                    elif 'youtu.be/' in video_url:
                        youtube_id = video_url.split('youtu.be/')[1].split('?')[0]
                        
                    logger.info(f"Extracted YouTube ID: {youtube_id}")
                except Exception as url_error:
                    logger.error(f"Error extracting YouTube ID: {url_error}")
                
                # Extract metadata from the original YouTube video URL
                try:
                    original_metadata = None
                    video_url = video.get('url', '')
                    
                    if video_url:
                        logger.info(f"Extracting metadata from original URL: {video_url}")
                        
                        # Use yt-dlp to extract comprehensive metadata
                        ydl_opts = {
                            'quiet': True,
                            'no_warnings': True,
                            'extract_flat': False,  # We need full metadata
                            'skip_download': True,
                            'youtube_include_dash_manifest': False,
                            'no_check_certificate': True,
                            'nocheckcertificate': True
                        }
                        
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            original_metadata = ydl.extract_info(video_url, download=False)
                            logger.info(f"Metadata extraction successful: {original_metadata.get('title')}")
                        
                        # Extract values from metadata
                        original_description = original_metadata.get('description', '')
                        original_tags = original_metadata.get('tags', [])
                        original_channel = original_metadata.get('uploader', 'Unknown')
                        
                        # Log extracted metadata
                        logger.info(f"Extracted description length: {len(original_description)}")
                        logger.info(f"Extracted tags count: {len(original_tags)}")
                        logger.info(f"Original channel: {original_channel}")
                    else:
                        logger.warning("No original URL found, using default metadata")
                        original_description = ""
                        original_tags = []
                        original_channel = "Unknown"
                except Exception as extract_error:
                    logger.error(f"Error extracting original metadata: {extract_error}")
                    # Default values if metadata extraction fails
                    original_description = ""
                    original_tags = []
                    original_channel = "Unknown"
                
                # Use original metadata with attribution
                description = original_description + f"\n\n[Uploaded via YouTube to Drive App]\nOriginal video: {video.get('url')}\nOriginal channel: {original_channel}"
                tags = original_tags if original_tags else ['youtube', 'upload', 'auto']
                
                logger.info(f"Using metadata with description length: {len(description)} and tag count: {len(tags)}")
                
                # Set privacy status
                if privacy_status not in ['public', 'private', 'unlisted']:
                    privacy_status = 'private'  # Default to private for safety
                
                # Prepare the API request body
                request_body = {
                    'snippet': {
                        'title': title,
                        'description': description,
                        'tags': tags,
                        'categoryId': '22'  # Category ID for "People & Blogs"
                    },
                    'status': {
                        'privacyStatus': privacy_status,
                        'selfDeclaredMadeForKids': False
                    }
                }
                
                # Execute the API request to actually upload the video
                logger.info(f"Starting YouTube upload for file: {file_path}")
                
                try:
                    # In production, this would use resumable upload
                    # For simplicity, we'll use a simpler approach for now
                    
                    # Create MediaFileUpload object for the video file with higher chunk size (50MB)
                    # for faster uploads
                    chunk_size = 52428800  # 50MB chunks instead of default 1MB
                    media = MediaFileUpload(
                        file_path,
                        mimetype='video/mp4',
                        resumable=True,
                        chunksize=chunk_size
                    )
                    
                    # Execute the API request with extra parameters for reliability
                    insert_request = youtube.videos().insert(
                        part=','.join(request_body.keys()),
                        body=request_body,
                        media_body=media,
                        notifySubscribers=False
                    )
                    
                    # The actual upload happens here with improved error handling
                    try:
                        # Using next_chunk for better control
                        status, response = None, None
                        while response is None:
                            status, response = insert_request.next_chunk()
                            if status:
                                percent = int(status.progress() * 100)
                                logger.info(f"Upload progress: {percent}%")
                                
                    except HttpError as e:
                        error_content = e.content.decode('utf-8') if hasattr(e, 'content') else str(e)
                        logger.error(f"YouTube API HTTP error: {error_content}")
                        if '<html>' in error_content:
                            return jsonify({'error': 'YouTube API returned HTML instead of JSON. This often indicates a network issue or API problem.'}), 500
                        raise
                    
                    if not response:
                        logger.error("Upload failed, response is None")
                        return jsonify({'error': 'Upload failed with empty response'}), 500
                    
                    # Extract the YouTube video ID from the response
                    youtube_video_id = response.get('id')
                    
                    if not youtube_video_id:
                        logger.error("YouTube upload succeeded but no video ID returned")
                        return jsonify({'error': 'Upload succeeded but no video ID returned'}), 500
                    
                    # Update the database with YouTube information
                    db.update_video(int(video_id), {
                        'uploaded_to_youtube': True,
                        'youtube_upload_id': youtube_video_id
                    })
                    
                    logger.info(f"YouTube upload successful. Video ID: {youtube_video_id}")
                    
                    # Return success response with video ID
                    return jsonify({
                        'status': 'success',
                        'youtube_video_id': youtube_video_id,
                        'message': 'Video successfully uploaded to YouTube'
                    })
                    
                except Exception as upload_error:
                    logger.error(f"YouTube API upload error: {upload_error}")
                    return jsonify({'error': f"YouTube upload error: {str(upload_error)}"}), 500
                
            except Exception as service_error:
                logger.error(f"Error creating YouTube service: {service_error}")
                return jsonify({'error': str(service_error)}), 500
            
        except Exception as e:
            logger.error(f"Error in YouTube upload with metadata: {e}")
            return jsonify({'error': f"YouTube upload error: {str(e)}"}), 500

    @app.route('/upload_to_youtube', methods=['POST'])
    def upload_to_youtube():
        """Upload video to YouTube with custom metadata"""
        try:
            # Check if user is logged in 
            if not hasattr(current_user, 'id') or current_user.is_anonymous:
                return jsonify({'error': 'You must be logged in to upload to YouTube'}), 401
                
            # Extract request data
            request_data = request.get_json()
            if not request_data:
                return jsonify({'error': 'Invalid request data'}), 400
                
            filename = request_data.get('filename')
            video_id = request_data.get('video_id')
            title = request_data.get('title', 'Uploaded video')
            description = request_data.get('description', '')
            tags = request_data.get('tags', '').split(',') if request_data.get('tags') else []
            privacy_status = request_data.get('privacy_status', 'private')
            
            # New option to use original metadata
            use_original_metadata = request_data.get('use_original_metadata', False)
            
            if not filename or not video_id:
                return jsonify({'error': 'Missing required parameters (filename or video_id)'}), 400
                
            # Get video information from database
            video = db.get_video_by_id(int(video_id))
            if not video:
                return jsonify({'error': 'Video not found in database'}), 404
                
            # Verify the file exists
            file_path = filename
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return jsonify({'error': 'Video file not found'}), 404
                
            # Get an authenticated YouTube service
            try:
                # Check if we have YouTube scope in the credentials
                if 'credentials' not in session:
                    logger.error("No credentials in session")
                    return jsonify({
                        'error': 'You need to authorize YouTube access',
                        'action_required': 'reauth'
                    }), 401
                
                # Check for YouTube scope in stored credentials
                credentials_data = json.loads(session['credentials'])
                scopes = credentials_data.get('scopes', [])
                
                logger.info(f"Available scopes for upload with custom metadata: {scopes}")
                
                # Check if we have YouTube upload scope
                youtube_scopes = ['https://www.googleapis.com/auth/youtube', 
                                 'https://www.googleapis.com/auth/youtube.upload']
                has_youtube_scope = any(scope in scopes for scope in youtube_scopes)
                
                if not has_youtube_scope:
                    logger.warning("Missing YouTube upload scope")
                    # Return a helpful error to guide user to re-authenticate
                    return jsonify({
                        'error': 'YouTube upload permission not granted. Please log out and log back in.',
                        'action_required': 'reauth'
                    }), 403
                    
                # Create YouTube service with credentials
                credentials_dict = {
                    'token': credentials_data.get('token'),
                    'refresh_token': credentials_data.get('refresh_token'),
                    'token_uri': credentials_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
                    'client_id': credentials_data.get('client_id'),
                    'client_secret': credentials_data.get('client_secret'),
                    'scopes': scopes
                }
                
                credentials = Credentials.from_authorized_user_info(credentials_dict)
                youtube = build('youtube', 'v3', credentials=credentials)
                
                # Extract metadata from original video if requested
                if use_original_metadata:
                    try:
                        video_url = video.get('url', '')
                        
                        if video_url:
                            logger.info(f"Extracting metadata from original URL for custom upload: {video_url}")
                            
                            # Use yt-dlp to extract comprehensive metadata
                            ydl_opts = {
                                'quiet': True,
                                'no_warnings': True,
                                'extract_flat': False,  # We need full metadata
                                'skip_download': True,
                                'youtube_include_dash_manifest': False,
                                'no_check_certificate': True,
                                'nocheckcertificate': True
                            }
                            
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                original_metadata = ydl.extract_info(video_url, download=False)
                                
                                # Override user-provided values with original metadata
                                if not title or title == 'Uploaded video':
                                    title = original_metadata.get('title', title)
                                if not description:
                                    description = original_metadata.get('description', '')
                                if not tags or len(tags) == 0:
                                    tags = original_metadata.get('tags', [])
                                
                                # Add attribution
                                description += f"\n\n[Uploaded via YouTube to Drive App]\nOriginal video: {video_url}\nOriginal channel: {original_metadata.get('uploader', 'Unknown')}"
                                
                                logger.info(f"Using original metadata: title='{title}', description length={len(description)}, tags count={len(tags)}")
                    except Exception as metadata_error:
                        logger.error(f"Error extracting original metadata for custom upload: {metadata_error}")
                        # Continue with user provided values
                
                # Validate tags (clean up empty strings and limit length)
                if tags:
                    tags = [tag.strip() for tag in tags if tag.strip()]
                    tags = tags[:30]  # YouTube limits to 30 tags
                else:
                    tags = ['youtube', 'upload']  # Default tags
                
                # Validate privacy status
                if privacy_status not in ['public', 'private', 'unlisted']:
                    privacy_status = 'private'  # Default to private for safety
                
                # Prepare the API request body
                request_body = {
                    'snippet': {
                        'title': title[:100],  # YouTube title length limit
                        'description': description[:5000],  # YouTube description length limit
                        'tags': tags,
                        'categoryId': '22'  # Category ID for "People & Blogs"
                    },
                    'status': {
                        'privacyStatus': privacy_status,
                        'selfDeclaredMadeForKids': False
                    }
                }
                
                # Execute the API request to actually upload the video
                logger.info(f"Starting YouTube upload with custom metadata for file: {file_path}")
                
                try:
                    # Create MediaFileUpload object for the video file with higher chunk size (50MB)
                    # for faster uploads
                    chunk_size = 52428800  # 50MB chunks instead of default 1MB
                    media = MediaFileUpload(
                        file_path, 
                        mimetype='video/mp4',
                        resumable=True,
                        chunksize=chunk_size
                    )
                    
                    # Execute the API request with extra parameters for reliability
                    insert_request = youtube.videos().insert(
                        part=','.join(request_body.keys()),
                        body=request_body,
                        media_body=media,
                        notifySubscribers=False
                    )
                    
                    # The actual upload happens here with improved error handling
                    try:
                        # Using next_chunk for better control
                        status, response = None, None
                        while response is None:
                            try:
                                status, response = insert_request.next_chunk()
                                if status:
                                    percent = int(status.progress() * 100)
                                    logger.info(f"Custom upload progress: {percent}%")
                            except ConnectionError as conn_err:
                                logger.error(f"Connection error during upload: {conn_err}")
                                time.sleep(5)  # Wait before retry
                            except Exception as chunk_err:
                                logger.error(f"Error during chunk upload: {chunk_err}")
                                if 'retry' in str(chunk_err).lower():
                                    time.sleep(5)  # Wait before retry
                                    continue
                                raise
                                
                    except HttpError as e:
                        error_content = e.content.decode('utf-8') if hasattr(e, 'content') else str(e)
                        logger.error(f"YouTube API HTTP error (custom upload): {error_content}")
                        if '<html>' in error_content:
                            # Special handling for HTML responses - could be OAuth/auth issues
                            if 'sign in' in error_content.lower() or 'auth' in error_content.lower():
                                return jsonify({'error': 'YouTube API authentication error. Please log out and log back in.', 'action_required': 'reauth'}), 401
                            
                            return jsonify({'error': 'YouTube API returned HTML instead of JSON. This often indicates a network issue or API problem.'}), 500
                        raise
                    
                    if not response:
                        logger.error("Upload failed, response is None")
                        return jsonify({'error': 'Upload failed with empty response'}), 500
                    
                    # Extract the YouTube video ID from the response
                    youtube_video_id = response.get('id')
                    
                    if not youtube_video_id:
                        logger.error("YouTube upload succeeded but no video ID returned")
                        return jsonify({'error': 'Upload succeeded but no video ID returned'}), 500
                    
                    # Update the database with YouTube information
                    db.update_video(int(video_id), {
                        'uploaded_to_youtube': True,
                        'youtube_upload_id': youtube_video_id
                    })
                    
                    logger.info(f"YouTube upload with custom metadata successful. Video ID: {youtube_video_id}")
                    
                    # Return success response with video ID
                    return jsonify({
                        'status': 'success',
                        'youtube_video_id': youtube_video_id,
                        'message': 'Video successfully uploaded to YouTube with custom metadata'
                    })
                    
                except Exception as upload_error:
                    logger.error(f"YouTube API upload error: {upload_error}")
                    return jsonify({'error': f"YouTube upload error: {str(upload_error)}"}), 500
                
            except Exception as service_error:
                logger.error(f"Error creating YouTube service: {service_error}")
                return jsonify({'error': str(service_error)}), 500
            
        except Exception as e:
            logger.error(f"Error in custom YouTube upload: {e}")
            return jsonify({'error': f"YouTube upload error: {str(e)}"}), 500

    @app.route('/download/<filename>', methods=['GET'])
    def download_file(filename):
        """Download a file to user's device"""
        try:
            # Sanitize filename
            safe_name = safe_filename(filename)
            
            # Find the file
            downloads_folder = temp_dir
            file_path = os.path.join(downloads_folder, safe_name)
            
            if not os.path.exists(file_path):
                return "File not found", 404
                
            # Set correct content type
            if file_path.endswith('.mp4'):
                content_type = 'video/mp4'
            elif file_path.endswith('.mp3'):
                content_type = 'audio/mpeg'
            else:
                content_type = 'application/octet-stream'
                
            return send_file(
                file_path,
                as_attachment=True,
                download_name=safe_name,
                mimetype=content_type
            )
        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            return str(e), 500

    @app.route('/get_history', methods=['GET'])
    def get_history():
        """Get download/upload history for the current user"""
        try:
            user_id = None
            if hasattr(current_user, 'id') and not current_user.is_anonymous:
                user_id = current_user.id
                
            # Get videos for the user
            if user_id:
                videos = db.get_user_videos(user_id)
            else:
                # If not logged in, return empty list
                videos = []
                
            # Return them as JSON
            return jsonify({
                'status': 'success',
                'videos': videos
            })
        except Exception as e:
            logger.error(f"Error getting history: {e}")
            return jsonify({'error': str(e)}), 500
            
    @app.route('/user_session', methods=['GET'])
    def user_session():
        """Get current user session data and associated download history"""
        try:
            if hasattr(current_user, 'id') and not current_user.is_anonymous:
                # User is logged in
                user_data = {
                    'id': current_user.id,
                    'username': current_user.username,
                    'email': current_user.email,
                    'authenticated': True
                }
                
                # Get download history for this user
                videos = db.get_user_videos(current_user.id)
            else:
                # User is not logged in
                user_data = {
                    'authenticated': False
                }
                videos = []
                
            return jsonify({
                'status': 'success',
                'user': user_data,
                'videos': videos
            })
        except Exception as e:
            logger.error(f"Error getting user session: {e}")
            return jsonify({'error': str(e)}), 500
            
    @app.route('/export_history', methods=['GET'])
    def export_user_history():
        """Export user's download history to a JSON file"""
        try:
            user_id = None
            if hasattr(current_user, 'id') and not current_user.is_anonymous:
                user_id = current_user.id
                
            # Get videos for this user
            if user_id:
                videos = db.get_user_videos(user_id)
                user_data = current_user.to_dict()
            else:
                # If not logged in, return empty data
                videos = []
                user_data = {'authenticated': False}
                
            # Create export data
            export_data = {
                'user': user_data,
                'videos': videos,
                'export_date': datetime.now().isoformat()
            }
            
            # Create a temporary file
            temp_file = os.path.join(temp_dir, f"export_history_{int(time.time())}.json")
            
            # Write data to file
            with open(temp_file, 'w') as f:
                json.dump(export_data, f, indent=2)
                
            # Return the file as download
            return send_file(
                temp_file,
                as_attachment=True,
                download_name="video_history_export.json",
                mimetype='application/json'
            )
        except Exception as e:
            logger.error(f"Error exporting history: {e}")
            return jsonify({'error': str(e)}), 500
            
    # Register all routes
    return app