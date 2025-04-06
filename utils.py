import os
import time
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def is_valid_youtube_url(url):
    """
    Validate if the provided URL is a valid YouTube URL
    
    Args:
        url (str): URL to validate
        
    Returns:
        bool: True if valid YouTube URL, False otherwise
    """
    try:
        parsed_url = urlparse(url)
        return ('youtube.com' in parsed_url.netloc or 
                'youtu.be' in parsed_url.netloc)
    except Exception as e:
        logger.error(f"Error validating YouTube URL: {e}")
        return False

def format_duration(seconds):
    """
    Format duration in seconds to HH:MM:SS format
    
    Args:
        seconds (int): Duration in seconds
        
    Returns:
        str: Formatted duration string
    """
    if not seconds:
        return "00:00"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"

def safe_filename(filename):
    """
    Create a safe filename by removing invalid characters
    
    Args:
        filename (str): Original filename
        
    Returns:
        str: Safe filename
    """
    return "".join([c for c in filename if c.isalpha() or 
                   c.isdigit() or c in ' ._-']).rstrip()

def generate_temp_filename(prefix="yt_video", extension="mp4"):
    """
    Generate a unique temporary filename
    
    Args:
        prefix (str): Filename prefix
        extension (str): File extension
        
    Returns:
        str: Generated filename
    """
    timestamp = int(time.time())
    return f"{prefix}_{timestamp}.{extension}"
