"""
Cache management routes.
"""

import logging
from flask import Blueprint, jsonify, request, g, current_app
from flask_limiter import Limiter
from datetime import datetime

from auth import AuthManager, require_auth

logger = logging.getLogger(__name__)
bp = Blueprint('cache', __name__)
limiter = None


def init_auth(manager: AuthManager, lim: Limiter):
    """Initialize auth manager and limiter"""
    global limiter
    limiter = lim


@bp.route('/refresh', methods=['POST'])
@require_auth
def refresh_devices():
    """Manually trigger device refresh"""
    try:
        device_service = current_app.extensions['device_service']
        
        logger.info("Manual device refresh triggered")
        devices = device_service.fetch_and_cache_devices()
        
        return jsonify({
            'message': 'Device refresh completed successfully',
            'devices_updated': len(devices),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Device refresh failed: {e}", exc_info=True)
        return jsonify({'error': {'code': 'REFRESH_FAILED', 'message': str(e)}}), 500


@bp.route('/cache/stats')
@require_auth
def get_cache_stats():
    """Get cache statistics"""
    try:
        device_cache = current_app.extensions['device_cache']
        stats = device_cache.get_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}", exc_info=True)
        return jsonify({'error': {'code': 'CACHE_STATS_FAILED', 'message': str(e)}}), 500


@bp.route('/cache/clear', methods=['POST'])
@require_auth
def clear_cache():
    """Clear the device cache"""
    try:
        device_cache = current_app.extensions['device_cache']
        device_cache.clear()
        logger.info("Cache cleared by user")
        return jsonify({'message': 'Cache cleared successfully'})
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}", exc_info=True)
        return jsonify({'error': {'code': 'CACHE_CLEAR_FAILED', 'message': str(e)}}), 500
