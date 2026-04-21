#!/usr/bin/env python3
"""
Lookout MRA Desktop Dashboard Launcher

This script provides an easy way to start the dashboard with proper configuration
and error handling for desktop deployment.
"""

import os
import sys
import logging
import webbrowser
import time
from threading import Timer

def setup_logging():
    """Setup logging for the launcher"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def check_dependencies():
    """Check if all required dependencies are installed"""
    logger = logging.getLogger(__name__)
    missing_deps = []
    
    try:
        import flask
        import requests
        import openpyxl
        from dotenv import load_dotenv  # This is how python-dotenv is imported
    except ImportError as e:
        missing_deps.append(str(e).split("'")[1])
    
    if missing_deps:
        logger.error("Missing required dependencies:")
        for dep in missing_deps:
            logger.error(f"  - {dep}")
        logger.error("Please install dependencies with: pip install -r requirements.txt")
        return False
    
    return True

def check_configuration():
    """Check basic configuration"""
    logger = logging.getLogger(__name__)
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Import config after loading env vars
    from config import get_config
    config_class = get_config()
    
    # Validate configuration
    issues = config_class.validate_config()
    if issues:
        logger.warning("Configuration issues found:")
        for issue in issues:
            logger.warning(f"  - {issue}")
        
        if not config_class.USE_SAMPLE_DATA:
            logger.error("Cannot start in production mode with configuration issues")
            return False
    
    return True

def open_browser(url, delay=2):
    """Open browser after a delay"""
    def _open():
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"Could not open browser automatically: {e}")
            print(f"Please open your browser and navigate to: {url}")
    
    Timer(delay, _open).start()

def main():
    """Main launcher function"""
    logger = setup_logging()
    
    print("="*60)
    print("🛡️  LOOKOUT MRA DESKTOP DASHBOARD")
    print("="*60)
    
    # Check dependencies
    logger.info("Checking dependencies...")
    if not check_dependencies():
        sys.exit(1)
    
    # Check configuration
    logger.info("Checking configuration...")
    if not check_configuration():
        sys.exit(1)
    
    # Import and start the app
    try:
        from config import get_config, print_config_summary
        config_class = get_config()
        
        # Print configuration summary
        print_config_summary()
        
        # Prepare browser URL
        url = f"http://{config_class.HOST}:{config_class.PORT}"
        
        print(f"🚀 Starting dashboard server...")
        print(f"📱 Dashboard will be available at: {url}")
        print(f"🔄 Mode: {'Sample Data' if config_class.USE_SAMPLE_DATA else 'Production API'}")
        print("="*60)
        
        # Open browser automatically (with delay)
        if config_class.HOST in ['127.0.0.1', 'localhost']:
            logger.info("Will open browser automatically in 3 seconds...")
            open_browser(url, delay=3)
        
        # Import and run the Flask app
        from app import create_app, _start_background_refresh_if_needed
        app = create_app()
        _start_background_refresh_if_needed(app)
        app.run(
            debug=config_class.DEBUG,
            host=config_class.HOST,
            port=config_class.PORT,
            threaded=config_class.ENABLE_THREADING
        )
        
    except KeyboardInterrupt:
        logger.info("Dashboard stopped by user")
        print("\n👋 Dashboard stopped. Thank you for using Lookout MRA Dashboard!")
        
    except Exception as e:
        logger.error(f"Failed to start dashboard: {e}")
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting tips:")
        print("1. Check that all dependencies are installed: pip install -r requirements.txt")
        print("2. Verify your .env file configuration")
        print("3. Ensure the port is not already in use")
        sys.exit(1)

if __name__ == '__main__':
    main()