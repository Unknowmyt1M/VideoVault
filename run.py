from main import app
import logging
import os
import threading
import time

# Import keep_alive module
try:
    from keep_alive import KeepAlive
    has_keep_alive = True
except ImportError:
    has_keep_alive = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def start_keep_alive():
    """Start the keep alive service in a separate thread"""
    if has_keep_alive:
        try:
            # Wait for the application to start
            time.sleep(10)
            
            # Start the keep alive monitor
            keep_alive = KeepAlive()
            keep_alive.start()
            logger.info("Keep-alive service started successfully")
        except Exception as e:
            logger.error(f"Failed to start keep-alive service: {e}")
    else:
        logger.warning("Keep-alive module not available. Application uptime monitoring disabled.")

if __name__ == '__main__':
    logger.info("Starting Flask application")
    
    # Determine if we should start the keep-alive service
    enable_keep_alive = os.environ.get('ENABLE_KEEP_ALIVE', 'true').lower() == 'true'
    
    if enable_keep_alive:
        # Start keep-alive in a separate thread so it doesn't block the main application
        keep_alive_thread = threading.Thread(target=start_keep_alive, daemon=True)
        keep_alive_thread.start()
        logger.info("Keep-alive thread initiated")
    
    # Start the Flask application
    app.run(host='0.0.0.0', port=5000, debug=True)