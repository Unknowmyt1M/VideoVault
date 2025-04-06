import json
import os
from datetime import datetime
import time

class JSONDatabase:
    """JSON file based database for storing application data"""
    
    def __init__(self, data_dir='data'):
        """Initialize the database with a data directory"""
        self.data_dir = data_dir
        # Create data directory if it doesn't exist
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Initialize database files if they don't exist
        self.users_file = os.path.join(self.data_dir, 'users.json')
        self.videos_file = os.path.join(self.data_dir, 'videos.json')
        
        if not os.path.exists(self.users_file):
            with open(self.users_file, 'w') as f:
                json.dump([], f)
                
        if not os.path.exists(self.videos_file):
            with open(self.videos_file, 'w') as f:
                json.dump([], f)
    
    def _load_data(self, file_path):
        """Load data from a JSON file"""
        with open(file_path, 'r') as f:
            return json.load(f)
    
    def _save_data(self, file_path, data):
        """Save data to a JSON file"""
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    # User operations
    def get_user_by_id(self, user_id):
        """Get user by ID"""
        users = self._load_data(self.users_file)
        for user in users:
            if user['id'] == user_id:
                return user
        return None
    
    def get_user_by_email(self, email):
        """Get user by email"""
        users = self._load_data(self.users_file)
        for user in users:
            if user['email'] == email:
                return user
        return None
    
    def create_user(self, username, email):
        """Create a new user"""
        users = self._load_data(self.users_file)
        # Check if user with email already exists
        for user in users:
            if user['email'] == email:
                return user
        
        # Create new user with a unique ID
        new_user = {
            'id': len(users) + 1,
            'username': username,
            'email': email,
            'created_at': datetime.utcnow().isoformat()
        }
        
        users.append(new_user)
        self._save_data(self.users_file, users)
        return new_user
    
    # Video operations
    def get_video_by_id(self, video_id):
        """Get video by ID"""
        videos = self._load_data(self.videos_file)
        for video in videos:
            if video['id'] == video_id:
                return video
        return None
    
    def create_video(self, video_data):
        """Create a new video record"""
        videos = self._load_data(self.videos_file)
        
        # Create new video with a unique ID
        new_video = {
            'id': len(videos) + 1,
            'youtube_id': video_data.get('youtube_id', ''),
            'title': video_data.get('title', 'Unknown'),
            'url': video_data.get('url', ''),
            'duration': video_data.get('duration', 0),
            'thumbnail_url': video_data.get('thumbnail_url', ''),
            'uploader': video_data.get('uploader', 'Unknown'),
            'download_date': datetime.utcnow().isoformat(),
            'file_size': video_data.get('file_size', 0),
            'download_success': video_data.get('download_success', False),
            'uploaded_to_drive': video_data.get('uploaded_to_drive', False),
            'drive_file_id': video_data.get('drive_file_id', None),
            'drive_folder_id': video_data.get('drive_folder_id', None),
            'uploaded_to_youtube': video_data.get('uploaded_to_youtube', False),
            'youtube_upload_id': video_data.get('youtube_upload_id', None),
            'user_id': video_data.get('user_id', None)
        }
        
        videos.append(new_video)
        self._save_data(self.videos_file, videos)
        return new_video
    
    def update_video(self, video_id, updated_data):
        """Update an existing video record"""
        videos = self._load_data(self.videos_file)
        
        for i, video in enumerate(videos):
            if video['id'] == video_id:
                # Update fields
                for key, value in updated_data.items():
                    videos[i][key] = value
                self._save_data(self.videos_file, videos)
                return videos[i]
        
        return None
    
    def get_user_videos(self, user_id):
        """Get all videos for a specific user"""
        videos = self._load_data(self.videos_file)
        user_videos = [video for video in videos if video.get('user_id') == user_id]
        # Sort by download date (newest first)
        user_videos.sort(key=lambda x: x.get('download_date', ''), reverse=True)
        return user_videos
    
    def get_all_videos(self):
        """Get all videos"""
        videos = self._load_data(self.videos_file)
        # Sort by download date (newest first)
        videos.sort(key=lambda x: x.get('download_date', ''), reverse=True)
        return videos