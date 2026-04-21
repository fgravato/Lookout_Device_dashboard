"""
Tenant and MDM routes.
"""

import logging
from flask import Blueprint, jsonify, request, g, current_app
from flask_limiter import Limiter

from auth import AuthManager, require_auth
from services.risk_service import RiskService
from utils.device_filters import apply_device_filters

logger = logging.getLogger(__name__)
bp = Blueprint('tenants', __name__)
limiter = None


def init_auth(manager: AuthManager, lim: Limiter):
    """Initialize auth manager and limiter"""
    global limiter
    limiter = lim


@bp.route('/tenants')
@require_auth
def get_tenants():
    """Get list of all tenants (multi-tenant mode only)"""
    try:
        config_class = current_app.extensions['config_class']
        tenant_service = current_app.extensions.get('tenant_service')
        
        if not config_class.ENABLE_MULTI_TENANT or not tenant_service:
            return jsonify({'error': {'code': 'MULTI_TENANT_DISABLED', 'message': 'Multi-tenant mode not enabled'}}), 400
        
        summary = tenant_service.get_tenants_summary()
        return jsonify(summary)
    except Exception as e:
        logger.error(f"Failed to get tenants: {e}", exc_info=True)
        return jsonify({'error': {'code': 'TENANT_FETCH_FAILED', 'message': 'Failed to fetch tenants'}}), 500


@bp.route('/tenants/<tenant_id>/devices')
@require_auth
def get_tenant_devices(tenant_id):
    """Get devices for a specific tenant"""
    try:
        device_service = current_app.extensions['device_service']
        config_class = current_app.extensions['config_class']
        
        cache_max_age = config_class.CACHE_MAX_AGE_MINUTES
        devices = device_service.get_cached_devices(cache_max_age)
        
        if devices is None:
            logger.info(f"Cache miss - fetching fresh device data for tenant {tenant_id}")
            devices = device_service.fetch_and_cache_devices()
        
        tenant_devices = [d for d in devices if d.get('tenant_id') == tenant_id]
        
        filtered_devices = apply_device_filters(tenant_devices, request.args, RiskService.analyze_device_risk)
        
        return jsonify({
            'devices': filtered_devices,
            'total_count': len(filtered_devices),
            'tenant_id': tenant_id
        })
        
    except Exception as e:
        logger.error(f"Failed to get tenant devices: {e}", exc_info=True)
        return jsonify({'error': {'code': 'TENANT_DEVICES_FAILED', 'message': str(e)}}), 500


@bp.route('/mdm/<mdm_identifier>/devices')
@require_auth
def get_mdm_devices(mdm_identifier):
    """Get devices by MDM identifier"""
    try:
        device_service = current_app.extensions['device_service']
        config_class = current_app.extensions['config_class']
        
        cache_max_age = config_class.CACHE_MAX_AGE_MINUTES
        devices = device_service.get_cached_devices(cache_max_age)
        
        if devices is None:
            logger.info(f"Cache miss - fetching fresh device data for MDM {mdm_identifier}")
            devices = device_service.fetch_and_cache_devices()
        
        mdm_devices = [d for d in devices if d.get('mdm_identifier') == mdm_identifier]
        
        filtered_devices = apply_device_filters(mdm_devices, request.args, RiskService.analyze_device_risk)
        
        return jsonify({
            'devices': filtered_devices,
            'total_count': len(filtered_devices),
            'mdm_identifier': mdm_identifier
        })
        
    except Exception as e:
        logger.error(f"Failed to get MDM devices: {e}", exc_info=True)
        return jsonify({'error': {'code': 'MDM_DEVICES_FAILED', 'message': str(e)}}), 500
