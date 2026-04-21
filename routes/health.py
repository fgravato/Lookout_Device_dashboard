"""
Health check route.
"""

import logging
from datetime import datetime
from flask import Blueprint, jsonify, current_app

logger = logging.getLogger(__name__)
bp = Blueprint('health', __name__)


@bp.route('/health')
def health_check():
    """Health check endpoint (no auth required)"""
    try:
        device_cache = current_app.extensions['device_cache']
        config_class = current_app.extensions['config_class']
        device_service = current_app.extensions['device_service']
        
        cache_stats = device_cache.get_stats()
        cache_age = cache_stats.get('cache_age_minutes', 0)
        
        checks = {
            'status': 'healthy',
            'cache': {
                'valid': device_cache.is_valid(config_class.CACHE_MAX_AGE_MINUTES),
                'device_count': cache_stats.get('cached_devices', 0),
                'age_minutes': cache_age,
                'last_updated': cache_stats.get('last_sync_time')
            },
            'api_client': not config_class.USE_SAMPLE_DATA and device_service.get_lookout_client() is not None,
            'sample_data_mode': config_class.USE_SAMPLE_DATA,
            'timestamp': datetime.now().isoformat()
        }
        
        if cache_age and cache_age > config_class.CACHE_MAX_AGE_MINUTES * 2:
            checks['status'] = 'degraded'
        
        return jsonify(checks), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({'error': {'code': 'HEALTH_CHECK_FAILED', 'message': 'Health check failed'}}), 503
