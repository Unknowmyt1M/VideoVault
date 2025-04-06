from datetime import datetime
import os
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_login import UserMixin

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

class User(UserMixin, db.Model):
    """User model for authentication"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    # Relationship with videos
    videos = db.relationship('Video', backref='user', lazy='dynamic')
    
    def __repr__(self):
        return f'<User {self.username}>'
        
    def to_dict(self):
        """Convert user object to dictionary"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email
        }

class Video(db.Model):
    """Model for tracking video downloads and uploads"""
    id = db.Column(db.Integer, primary_key=True)
    youtube_id = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(255), nullable=False)
    duration = db.Column(db.Integer, nullable=True)
    thumbnail_url = db.Column(db.String(255), nullable=True)
    uploader = db.Column(db.String(255), nullable=True)
    download_date = db.Column(db.DateTime, default=datetime.utcnow)
    file_size = db.Column(db.BigInteger, nullable=True)
    download_success = db.Column(db.Boolean, default=False)
    uploaded_to_drive = db.Column(db.Boolean, default=False)
    drive_file_id = db.Column(db.String(100), nullable=True)
    drive_folder_id = db.Column(db.String(100), nullable=True)
    # New fields for YouTube uploading
    uploaded_to_youtube = db.Column(db.Boolean, default=False)
    youtube_upload_id = db.Column(db.String(100), nullable=True)
    # User relationship
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    def __repr__(self):
        return f'<Video {self.title}>'
    
    def to_dict(self):
        """Convert video object to dictionary"""
        return {
            'id': self.id,
            'youtube_id': self.youtube_id,
            'title': self.title,
            'url': self.url,
            'duration': self.duration,
            'thumbnail_url': self.thumbnail_url,
            'uploader': self.uploader,
            'download_date': self.download_date.isoformat() if self.download_date else None,
            'file_size': self.file_size,
            'download_success': self.download_success,
            'uploaded_to_drive': self.uploaded_to_drive,
            'drive_file_id': self.drive_file_id,
            'drive_folder_id': self.drive_folder_id,
            'uploaded_to_youtube': self.uploaded_to_youtube,
            'youtube_upload_id': self.youtube_upload_id,
            'user_id': self.user_id,
            'user': self.user.to_dict() if self.user else None
        }