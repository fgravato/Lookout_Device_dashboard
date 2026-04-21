"""
Lookout Device Report Dashboard - Flask Application

Refactored with:
- Blueprint-based route organization
- AuthManager extracted to auth module
- ExportService refactored into sheet modules
- App factory pattern for better testability
"""

import os
import json
import logging
import threading
import time as time_module
from datetime import datetime
from typing import Dict, Optional, Tuple, Any

from flask import Flask, jsonify, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

from config import get_config, print_config_summary
from lookout_client import LookoutMRAClient, LookoutAPIError
from device_cache import DeviceCache, enhanced_device_mapping
from services.device_service import DeviceService
from services.export import ExportService
from services.cve_service import CVEService
from services.tenant_service import TenantService
from auth import AuthManager
from routes import health, cache, devices, tenants, export, cve

logger = logging.getLogger(__name__)


# =============================================================================
# Standardized Error Response Helpers
# =============================================================================

class APIError(Exception):
    """Custom exception for API errors with standardized response format"""
    def __init__(self, code: str, message: str, status_code: int = 500, details: Optional[Dict] = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'error': {
                'code': self.code,
                'message': self.message,
                **self.details
            }
        }


def error_response(code: str, message: str, status_code: int = 500, details: Optional[Dict] = None) -> Tuple[Dict, int]:
    """Create a standardized error response"""
    response = {
        'error': {
            'code': code,
            'message': message
        }
    }
    if details:
        response['error'].update(details)
    return jsonify(response), status_code


def success_response(data: Any, status_code: int = 200) -> Tuple[Dict, int]:
    """Create a standardized success response"""
    return jsonify(data), status_code


# =============================================================================
# Application Factory
# =============================================================================

def create_app(config_name: Optional[str] = None) -> Flask:
    """
    Application factory for creating Flask app instances.
    
    Args:
        config_name: Optional config name ('development', 'production', 'testing')
        
    Returns:
        Configured Flask application
    """
    load_dotenv()
    
    config_class = get_config(config_name)
    
    log_level = getattr(logging, config_class.LOG_LEVEL, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        filename=config_class.LOG_FILE if config_class.LOG_FILE else None
    )
    
    issues = config_class.validate_config()
    if issues:
        for issue in issues:
            logger.warning(f"Config issue: {issue}")
    
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.secret_key = config_class.SECRET_KEY
    
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"]
    )
    
    auth_manager = AuthManager(config_class)
    
    device_cache = DeviceCache(
        enable_persistence=config_class.ENABLE_DISK_CACHE,
        cache_file=config_class.CACHE_FILE_PATH
    )
    
    tenant_service = None
    if config_class.ENABLE_MULTI_TENANT:
        try:
            tenant_service = TenantService(config_class.TENANTS_CONFIG_FILE)
            logger.info(f"Multi-tenant mode enabled with {len(tenant_service.tenants)} tenants")
        except Exception as e:
            logger.error(f"Failed to initialize tenant service: {e}")
    
    device_service = DeviceService(config_class, device_cache, tenant_service)
    export_service = ExportService(device_service)
    
    app.extensions = {
        'config_class': config_class,
        'limiter': limiter,
        'auth_manager': auth_manager,
        'device_cache': device_cache,
        'tenant_service': tenant_service,
        'device_service': device_service,
        'export_service': export_service,
        'cve_service': None
    }
    
    # Initialize blueprints with auth and limiter
    cache.init_auth(auth_manager, limiter)
    devices.init_auth(auth_manager, limiter)
    tenants.init_auth(auth_manager, limiter)
    export.init_auth(auth_manager, limiter)
    cve.init_auth(auth_manager, limiter)
    
    # Register blueprints
    app.register_blueprint(health.bp)
    app.register_blueprint(cache.bp, url_prefix='/api')
    app.register_blueprint(devices.bp)
    app.register_blueprint(tenants.bp, url_prefix='/api')
    app.register_blueprint(export.bp, url_prefix='/api')
    app.register_blueprint(cve.bp, url_prefix='/api')
    
    register_error_handlers(app)
    
    if config_class.AUTO_REFRESH_ON_STARTUP:
        initialize_device_cache(app, device_service, device_cache, config_class)
    
    return app


# =============================================================================
# Error Handlers
# =============================================================================

def register_error_handlers(app: Flask):
    """Register error handlers for the application"""
    
    @app.errorhandler(APIError)
    def handle_api_error(error):
        return error.to_dict(), error.status_code
    
    @app.errorhandler(400)
    def bad_request(error):
        return error_response('BAD_REQUEST', 'Bad request', 400)
    
    @app.errorhandler(401)
    def unauthorized(error):
        return error_response('UNAUTHORIZED', 'Authentication required', 401)
    
    @app.errorhandler(404)
    def not_found(error):
        return error_response('NOT_FOUND', 'Resource not found', 404)
    
    @app.errorhandler(429)
    def rate_limit(error):
        return error_response('RATE_LIMIT', 'Rate limit exceeded', 429)
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal server error: {error}", exc_info=True)
        return error_response('INTERNAL_ERROR', 'Internal server error', 500)
    
    @app.errorhandler(503)
    def service_unavailable(error):
        return error_response('SERVICE_UNAVAILABLE', 'Service temporarily unavailable', 503)


# =============================================================================
# Cache Initialization
# =============================================================================

def initialize_device_cache(app: Flask, device_service: DeviceService, 
                            device_cache: DeviceCache, config_class):
    """Initialize device cache on startup if needed"""
    try:
        if not device_cache.is_valid(config_class.CACHE_MAX_AGE_MINUTES):
            logger.info("Cache empty or stale - loading initial device data")
            with app.app_context():
                device_service.fetch_and_cache_devices()
                logger.info("Initial device data loaded successfully")
        else:
            logger.info("Using existing cache from previous session")
    except Exception as e:
        logger.error(f"Failed to initialize device cache: {e}")


# =============================================================================
# Background Refresh
# =============================================================================

def start_background_refresh(app: Flask, device_service: DeviceService, 
                             device_cache: DeviceCache, config_class):
    """Start background refresh worker thread"""
    
    def background_refresh_worker():
        """Background worker that periodically refreshes device data"""
        while not _shutdown_event.is_set():
            try:
                # Use event wait instead of sleep for responsive shutdown
                if _shutdown_event.wait(timeout=config_class.BACKGROUND_REFRESH_INTERVAL_MINUTES * 60):
                    break  # Shutdown requested

                if not device_cache.is_valid(config_class.CACHE_MAX_AGE_MINUTES):
                    logger.info("Background refresh: Cache stale, refreshing device data")
                    with app.app_context():
                        device_service.fetch_and_cache_devices()
                        logger.info("Background refresh: Device data updated successfully")
                else:
                    logger.debug("Background refresh: Cache still valid, skipping refresh")

            except Exception as e:
                logger.error(f"Background refresh error: {e}", exc_info=True)
                if _shutdown_event.wait(timeout=60):
                    break
    
    refresh_thread = threading.Thread(target=background_refresh_worker, daemon=True)
    refresh_thread.start()
    logger.info(f"Background refresh started (interval: {config_class.BACKGROUND_REFRESH_INTERVAL_MINUTES} minutes)")


# =============================================================================
# Application Entry Point
# =============================================================================

# Shutdown event for graceful background thread termination
_shutdown_event = threading.Event()


def _start_background_refresh_if_needed(app: Flask):
    """Start background refresh if configured"""
    config_class = app.extensions['config_class']
    if not config_class.USE_SAMPLE_DATA and config_class.BACKGROUND_REFRESH_ENABLED:
        start_background_refresh(
            app,
            app.extensions['device_service'],
            app.extensions['device_cache'],
            config_class
        )


def get_app() -> Flask:
    """Get or create the Flask application (lazy singleton for WSGI/gunicorn)"""
    global _app_instance
    if '_app_instance' not in globals() or _app_instance is None:
        _app_instance = create_app()
        _start_background_refresh_if_needed(_app_instance)
    return _app_instance

_app_instance = None


if __name__ == '__main__':
    app = create_app()
    config_class = app.extensions['config_class']

    _start_background_refresh_if_needed(app)

    if config_class.USE_SAMPLE_DATA:
        logger.info("Starting in development mode with sample data")
    else:
        logger.info("Starting in production mode")

    app.run(
        debug=config_class.DEBUG,
        host=config_class.HOST,
        port=config_class.PORT
    )
