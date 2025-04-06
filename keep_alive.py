#!/usr/bin/env python3
"""
Keep Alive Script for Flask Application
This script helps maintain application uptime by continuously pinging 
the application and restarting it if needed.
"""

import os
import sys
import time
import logging
import threading
import subprocess
import requests
from datetime import datetime, timedelta

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('keep_alive.log')
    ]
)
logger = logging.getLogger('keep_alive')

# Configuration
APP_URL = os.environ.get('APP_URL', 'http://localhost:5000')
PING_INTERVAL = int(os.environ.get('PING_INTERVAL', 300))  # In seconds (default: 5 minutes)
RESTART_THRESHOLD = int(os.environ.get('RESTART_THRESHOLD', 3))  # Number of failed pings before restart
MAX_RESTART_ATTEMPTS = int(os.environ.get('MAX_RESTART_ATTEMPTS', 5))  # Maximum restart attempts
RESTART_COOLDOWN = int(os.environ.get('RESTART_COOLDOWN', 1800))  # Seconds to wait between restarts (default: 30 minutes)

# Replit-specific configuration
IS_REPLIT = 'REPLIT_DB_URL' in os.environ
REPLIT_KEEP_ALIVE = bool(int(os.environ.get('REPLIT_KEEP_ALIVE', '1')))
REPLIT_AUTO_RESTART = bool(int(os.environ.get('REPLIT_AUTO_RESTART', '1')))
REPLIT_RESTART_COMMAND = os.environ.get('REPLIT_RESTART_COMMAND', 'kill 1')  # In Replit, kill 1 restarts the application

class KeepAlive:
    """
    A class to continuously monitor and keep a web application alive.
    """
    def __init__(self):
        self.app_url = APP_URL
        self.ping_interval = PING_INTERVAL
        self.restart_threshold = RESTART_THRESHOLD
        self.max_restart_attempts = MAX_RESTART_ATTEMPTS
        self.restart_cooldown = RESTART_COOLDOWN
        self.is_replit = IS_REPLIT
        self.failed_pings = 0
        self.restart_attempts = 0
        self.last_restart_time = datetime.min
        self.running = False
        self.thread = None

    def ping_app(self):
        """Ping the application to check if it's alive"""
        try:
            logger.info(f"Pinging application at {self.app_url}")
            response = requests.get(self.app_url, timeout=10)
            if response.status_code == 200:
                logger.info("Application is alive")
                self.failed_pings = 0
                return True
            else:
                logger.warning(f"Application responded with status code {response.status_code}")
                self.failed_pings += 1
                return False
        except Exception as e:
            logger.error(f"Failed to ping application: {e}")
            self.failed_pings += 1
            return False

    def restart_app(self):
        """Restart the application"""
        if self.restart_attempts >= self.max_restart_attempts:
            logger.error(f"Maximum restart attempts ({self.max_restart_attempts}) reached. Giving up.")
            return False

        # Check if cooldown period has elapsed
        now = datetime.now()
        cooldown_delta = now - self.last_restart_time
        if cooldown_delta < timedelta(seconds=self.restart_cooldown):
            seconds_left = (timedelta(seconds=self.restart_cooldown) - cooldown_delta).total_seconds()
            logger.info(f"Cooldown period not elapsed. Waiting {seconds_left:.0f} seconds before next restart.")
            return False

        logger.info("Attempting to restart application")
        try:
            if self.is_replit and REPLIT_AUTO_RESTART:
                logger.info("Restarting Replit application using kill 1 command")
                os.system(REPLIT_RESTART_COMMAND)
            else:
                # For non-Replit environments, you could add custom restart logic here
                logger.info("Custom restart logic for non-Replit environments")
                # Example: subprocess.run(["systemctl", "restart", "flask-app.service"])
                
            self.restart_attempts += 1
            self.last_restart_time = now
            logger.info(f"Application restart attempt {self.restart_attempts} completed")
            return True
        except Exception as e:
            logger.error(f"Failed to restart application: {e}")
            return False

    def check_and_restart(self):
        """Check application status and restart if necessary"""
        if not self.ping_app():
            logger.warning(f"Failed ping count: {self.failed_pings}/{self.restart_threshold}")
            if self.failed_pings >= self.restart_threshold:
                logger.warning("Threshold reached, attempting to restart")
                self.restart_app()
                # Reset failed pings counter after restart attempt
                self.failed_pings = 0

    def monitor_loop(self):
        """Main monitoring loop"""
        while self.running:
            self.check_and_restart()
            time.sleep(self.ping_interval)

    def start(self):
        """Start the monitoring thread"""
        if self.thread and self.thread.is_alive():
            logger.info("Monitor already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.thread.start()
        logger.info("Application monitoring started")

    def stop(self):
        """Stop the monitoring thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5.0)
        logger.info("Application monitoring stopped")

def setup_replit_keep_alive():
    """Set up Replit-specific keep alive configuration"""
    if not IS_REPLIT or not REPLIT_KEEP_ALIVE:
        return None
        
    logger.info("Setting up Replit-specific keep alive")
    
    # Create a Flask route to handle keep-alive pings if needed
    try:
        from app import app
        
        @app.route('/ping')
        def ping():
            """Simple ping endpoint for health checks"""
            return "pong", 200
            
        logger.info("Added /ping endpoint to Flask application")
    except ImportError:
        logger.warning("Could not import Flask app, skipping ping endpoint setup")
    
    return True

def main():
    """Main function to start the keep alive process"""
    logger.info("Starting keep alive service")
    
    # Set up Replit-specific configuration
    if IS_REPLIT:
        setup_replit_keep_alive()
    
    # Start monitoring
    monitor = KeepAlive()
    monitor.start()
    
    try:
        # Keep the main thread alive
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down")
        monitor.stop()
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
        monitor.stop()
        raise

if __name__ == "__main__":
    main()