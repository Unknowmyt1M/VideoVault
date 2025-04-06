#!/usr/bin/env python3
"""
Replit Deployment Configuration Script

This script helps configure and manage deployments on Replit.
It can be used to set up scheduled deployments, environment variables, and 
maintain application uptime.

Usage:
1. Run this script to configure deployment settings
2. Use it to update environment variables
3. Schedule regular deployments
"""

import os
import sys
import json
import argparse
import logging
import subprocess
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('deployment.log')
    ]
)
logger = logging.getLogger('replit_deployment')

class ReplitDeployment:
    """Manages deployment configuration for Replit"""
    
    def __init__(self):
        """Initialize the deployment manager"""
        self.config_file = ".replit.deployment.json"
        self.config = self._load_config()
        
    def _load_config(self):
        """Load existing configuration or create default"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading config: {e}")
                
        # Default configuration
        return {
            "auto_deploy": False,
            "schedule": {
                "enabled": False,
                "frequency": "daily",  # daily, hourly, weekly
                "time": "00:00",  # for daily/weekly
                "day": 1,  # 1-7 for weekly (Monday=1)
            },
            "keep_alive": {
                "enabled": True,
                "ping_interval": 300,  # seconds
                "restart_threshold": 3
            },
            "environment": {
                "production": True,
                "debug": False
            },
            "last_deployment": None,
            "deployment_count": 0
        }
    
    def save_config(self):
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.info("Configuration saved successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            return False
    
    def set_schedule(self, enabled=True, frequency="daily", time="00:00", day=1):
        """Set deployment schedule"""
        self.config["schedule"] = {
            "enabled": enabled,
            "frequency": frequency,
            "time": time,
            "day": day
        }
        logger.info(f"Schedule updated: {frequency} at {time}")
        return self.save_config()
    
    def set_keep_alive(self, enabled=True, ping_interval=300, restart_threshold=3):
        """Set keep-alive configuration"""
        self.config["keep_alive"] = {
            "enabled": enabled,
            "ping_interval": ping_interval,
            "restart_threshold": restart_threshold
        }
        # Update environment variables for keep-alive script
        os.environ['ENABLE_KEEP_ALIVE'] = str(enabled).lower()
        os.environ['PING_INTERVAL'] = str(ping_interval)
        os.environ['RESTART_THRESHOLD'] = str(restart_threshold)
        
        logger.info(f"Keep-alive configuration updated: enabled={enabled}")
        return self.save_config()
    
    def set_environment_mode(self, production=True, debug=False):
        """Set environment mode"""
        self.config["environment"] = {
            "production": production,
            "debug": debug
        }
        # Update environment variables
        os.environ['FLASK_ENV'] = 'production' if production else 'development'
        os.environ['FLASK_DEBUG'] = '1' if debug else '0'
        
        logger.info(f"Environment mode set to: {'production' if production else 'development'}")
        return self.save_config()
    
    def record_deployment(self):
        """Record a deployment event"""
        now = datetime.now().isoformat()
        self.config["last_deployment"] = now
        self.config["deployment_count"] += 1
        logger.info(f"Deployment recorded. Total deployments: {self.config['deployment_count']}")
        return self.save_config()
    
    def setup_auto_deployment(self):
        """Set up automatic deployment"""
        self.config["auto_deploy"] = True
        
        # Create .replit file if it doesn't exist
        if not os.path.exists(".replit"):
            with open(".replit", "w") as f:
                f.write("[nix]\n")
                f.write("channel = \"stable-22_11\"\n\n")
                f.write("[deployment]\n")
                f.write("run = [\"python3\", \"run.py\"]\n")
                f.write("deploymentTarget = \"cloudrun\"\n")
                f.write("ignorePorts = false\n")
                f.write("autoDeploy = true\n")
                
            logger.info("Created .replit configuration with auto-deployment")
        
        return self.save_config()
    
    def configure_scheduled_run(self):
        """Configure Replit's scheduled runs feature"""
        try:
            if not os.path.exists(".replit"):
                logger.error(".replit file doesn't exist. Run setup_auto_deployment first.")
                return False
                
            # Add scheduled run configuration to .replit file
            with open(".replit", "a") as f:
                f.write("\n[scheduled_runs]\n")
                f.write("keep_alive = {\"\", \"0 */6 * * *\", \"python3 keep_alive.py\"}\n")
                
            logger.info("Configured scheduled runs in .replit")
            return True
        except Exception as e:
            logger.error(f"Error configuring scheduled runs: {e}")
            return False
    
    def print_status(self):
        """Print current deployment status"""
        print("\n--- Replit Deployment Status ---")
        print(f"Auto-deploy: {self.config['auto_deploy']}")
        print(f"Schedule: {self.config['schedule']}")
        print(f"Keep-alive: {self.config['keep_alive']}")
        print(f"Environment: {self.config['environment']}")
        print(f"Last deployment: {self.config['last_deployment']}")
        print(f"Total deployments: {self.config['deployment_count']}")
        print("------------------------------\n")
    
    def update_environment_variables(self, env_vars):
        """Update environment variables for deployment"""
        try:
            env_path = ".env"
            
            # Start with existing variables
            existing_vars = {}
            if os.path.exists(env_path):
                with open(env_path, "r") as f:
                    for line in f:
                        if "=" in line and not line.startswith("#"):
                            key, value = line.strip().split("=", 1)
                            existing_vars[key] = value
            
            # Update with new variables
            existing_vars.update(env_vars)
            
            # Write back to file
            with open(env_path, "w") as f:
                for key, value in existing_vars.items():
                    f.write(f"{key}={value}\n")
            
            logger.info(f"Updated {len(env_vars)} environment variables in {env_path}")
            return True
        except Exception as e:
            logger.error(f"Error updating environment variables: {e}")
            return False

def main():
    """Main function to handle CLI arguments"""
    parser = argparse.ArgumentParser(description="Replit Deployment Configuration")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Initialize command
    init_parser = subparsers.add_parser("init", help="Initialize deployment configuration")
    
    # Schedule command
    schedule_parser = subparsers.add_parser("schedule", help="Set deployment schedule")
    schedule_parser.add_argument("--enable", action="store_true", help="Enable scheduled deployment")
    schedule_parser.add_argument("--disable", action="store_true", help="Disable scheduled deployment")
    schedule_parser.add_argument("--frequency", choices=["hourly", "daily", "weekly"], 
                                help="Deployment frequency")
    schedule_parser.add_argument("--time", help="Deployment time (HH:MM)")
    schedule_parser.add_argument("--day", type=int, choices=range(1, 8), 
                                help="Day of week for weekly schedule (1=Monday)")
    
    # Keep-alive command
    keepalive_parser = subparsers.add_parser("keepalive", help="Configure keep-alive settings")
    keepalive_parser.add_argument("--enable", action="store_true", help="Enable keep-alive")
    keepalive_parser.add_argument("--disable", action="store_true", help="Disable keep-alive")
    keepalive_parser.add_argument("--interval", type=int, help="Ping interval in seconds")
    keepalive_parser.add_argument("--threshold", type=int, help="Restart threshold")
    
    # Environment command
    env_parser = subparsers.add_parser("env", help="Set environment mode")
    env_parser.add_argument("--production", action="store_true", help="Set production mode")
    env_parser.add_argument("--development", action="store_true", help="Set development mode")
    env_parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    
    # Status command
    subparsers.add_parser("status", help="Show deployment status")
    
    # Auto-deploy command
    auto_parser = subparsers.add_parser("auto", help="Configure auto-deployment")
    auto_parser.add_argument("--enable", action="store_true", help="Enable auto-deployment")
    auto_parser.add_argument("--scheduled-runs", action="store_true", help="Configure scheduled runs")
    
    args = parser.parse_args()
    
    # Create deployment manager
    deployment = ReplitDeployment()
    
    if args.command == "init":
        deployment.save_config()
        print("Initialized deployment configuration")
    
    elif args.command == "schedule":
        if args.enable:
            frequency = args.frequency or "daily"
            time = args.time or "00:00"
            day = args.day or 1
            deployment.set_schedule(True, frequency, time, day)
        elif args.disable:
            deployment.set_schedule(False)
        else:
            # Just update values if provided
            schedule = deployment.config["schedule"]
            frequency = args.frequency or schedule["frequency"]
            time = args.time or schedule["time"]
            day = args.day or schedule["day"]
            deployment.set_schedule(schedule["enabled"], frequency, time, day)
    
    elif args.command == "keepalive":
        if args.enable:
            interval = args.interval or 300
            threshold = args.threshold or 3
            deployment.set_keep_alive(True, interval, threshold)
        elif args.disable:
            deployment.set_keep_alive(False)
        else:
            # Just update values if provided
            keep_alive = deployment.config["keep_alive"]
            interval = args.interval or keep_alive["ping_interval"]
            threshold = args.threshold or keep_alive["restart_threshold"]
            deployment.set_keep_alive(keep_alive["enabled"], interval, threshold)
    
    elif args.command == "env":
        production = True
        debug = False
        
        if args.development:
            production = False
        if args.debug:
            debug = True
            
        deployment.set_environment_mode(production, debug)
    
    elif args.command == "auto":
        if args.enable:
            deployment.setup_auto_deployment()
            print("Auto-deployment enabled")
        
        if args.scheduled_runs:
            if deployment.configure_scheduled_run():
                print("Scheduled runs configured")
    
    elif args.command == "status" or not args.command:
        deployment.print_status()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())