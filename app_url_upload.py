# Upload URL to Telegram endpoint
import os
import time
import json
import logging
import mimetypes
import tempfile
from datetime import datetime
from urllib.parse import urlparse
import requests
from flask import request, jsonify
from flask_login import login_required, current_user

from utils import is_valid_youtube_url, safe_filename
from telegram_utils import upload_file_sync

# Set up logging
logger = logging.getLogger(__name__)

# Create temporary directory if it doesn't exist
temp_dir = os.path.join(tempfile.gettempdir(), 'videovault_temp')
os.makedirs(temp_dir, exist_ok=True)

# This function will be registered with the Flask app
@login_required  # Ensure user is logged in
def upload_url_to_telegram():
    """Upload file from URL to Telegram storage in chunks"""
    try:
        logger.info("Starting URL Upload To Cloud process")
        data = request.get_json()
        if not data or 'url' not in data:
            logger.error("No URL provided in request")
            return jsonify({'success': False, 'error': 'No URL provided'}), 400
            
        url = data.get('url')
        custom_filename = data.get('filename')
        
        logger.info(f"Received URL upload request: {url[:50]}{'...' if len(url) > 50 else ''}")
        
        # Check if URL is valid
        if not url.startswith(('http://', 'https://')):
            logger.error(f"Invalid URL format: {url[:50]}")
            return jsonify({'success': False, 'error': 'Invalid URL format'}), 400
            
        # For YouTube URLs, redirect to the normal download flow
        if is_valid_youtube_url(url):
            logger.info(f"YouTube URL detected, redirecting to download page")
            return jsonify({
                'success': False,
                'error': 'For YouTube videos, please use the main download page',
                'redirect': '/download'
            }), 200
        
        # Get filename from URL if not provided
        if not custom_filename:
            parsed_url = urlparse(url)
            custom_filename = os.path.basename(parsed_url.path)
            # If filename is empty or has no extension, generate one
            if not custom_filename or '.' not in custom_filename:
                custom_filename = f"download_{int(time.time())}.bin"
                
        logger.info(f"Downloading from URL: {url} with filename: {custom_filename}")
        
        # Create a temporary file path
        temp_file_path = os.path.join(temp_dir, safe_filename(custom_filename))
        
        # Download the file from the URL
        try:
            # Stream the download to save memory
            with requests.get(url, stream=True, timeout=300) as response:
                response.raise_for_status()
                
                # Get content length if available
                total_size = int(response.headers.get('content-length', 0))
                
                # Get content type and adjust filename if needed
                content_type = response.headers.get('content-type', '')
                if not custom_filename or '.' not in custom_filename:
                    # Try to guess extension from content type
                    extension = mimetypes.guess_extension(content_type)
                    if extension:
                        custom_filename = f"download_{int(time.time())}{extension}"
                        temp_file_path = os.path.join(temp_dir, safe_filename(custom_filename))
                
                # Open file for writing
                with open(temp_file_path, 'wb') as f:
                    # Track progress
                    downloaded = 0
                    chunk_size = 8192  # 8KB chunks
                    
                    # Download in chunks
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            # Log progress for larger files
                            if total_size > 10*1024*1024 and downloaded % (1024*1024) == 0:  # Every 1MB
                                logger.info(f"Downloaded {downloaded/(1024*1024):.2f}MB of {total_size/(1024*1024):.2f}MB")
                                
            logger.info(f"Download from URL completed: {temp_file_path}")
            
            # Get user info for caption
            user_email = current_user.email if hasattr(current_user, 'email') else "Unknown"
            user_name = current_user.username if hasattr(current_user, 'username') else "Unknown User"
            
            # Current date and time for caption
            upload_date = datetime.now().strftime("%d %B, %Y")
            upload_time = datetime.now().strftime("%H:%M")
            
            # Create caption with requested format
            caption = f"Title: {custom_filename}\nUploaded by: {user_name} ({user_email})\nUpload time: uploaded on {upload_date} at {upload_time}\nSource URL: {url}"
            
            # Upload To Cloud with enhanced caption
            try:
                logger.info(f"Uploading file to Telegram: {temp_file_path}")
                chunks_metadata = upload_file_sync(temp_file_path, caption)
                logger.info(f"Telegram upload successful: {chunks_metadata.get('chunks', 0)} chunks")
                
                # Remove temporary file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    logger.info(f"Removed temporary file: {temp_file_path}")
                    
                return jsonify({
                    'success': True,
                    'message': f"File downloaded from URL and uploaded to Telegram ({chunks_metadata.get('chunks', 0)} chunks)",
                    'metadata': chunks_metadata
                })
            except Exception as e:
                logger.error(f"Error uploading to Telegram: {e}")
                # Clean up temp file if it exists
                if os.path.exists(temp_file_path):
                    try:
                        os.unlink(temp_file_path)
                        logger.info(f"Cleaned up temporary file after error: {temp_file_path}")
                    except Exception as cleanup_error:
                        logger.error(f"Failed to clean up temporary file: {cleanup_error}")
                
                return jsonify({
                    'success': False, 
                    'error': f"Failed to Upload To Cloud: {str(e)}"
                }), 500
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error downloading from URL: {e}")
            return jsonify({
                'success': False, 
                'error': f"Failed to download from URL: {str(e)}"
            }), 500
                
    except Exception as e:
        logger.error(f"Error in upload_url_to_telegram: {e}")
        return jsonify({
            'success': False, 
            'error': f"Upload process failed: {str(e)}"
        }), 500