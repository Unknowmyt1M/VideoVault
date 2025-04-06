import logging
from flask import render_template, redirect, url_for, flash, jsonify, request
from flask_login import LoginManager, current_user, login_required
from main import db

# Configure logging
logger = logging.getLogger(__name__)

def init_routes(app):
    """Initialize routes and Flask-Login"""
    # Set up login manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'google_auth.login'
    
    @login_manager.user_loader
    def load_user(user_id):
        from models import User
        return User.query.get(int(user_id))
    
    @app.route('/')
    def index():
        logger.info("Loading index page")
        return render_template('index.html')
    
    @app.route('/dashboard')
    def dashboard():
        logger.info("Loading dashboard page")
        return render_template('dashboard.html')
    
    @app.route('/download')
    def download():
        logger.info("Loading download page")
        return render_template('download.html')
    
    @app.route('/history')
    def history():
        logger.info("Loading history page")
        # Placeholder for videos from database
        videos = []
        return render_template('history.html', videos=videos)
    
    # Import and register Google Auth blueprint
    from google_auth import google_auth
    app.register_blueprint(google_auth)
    
    return app