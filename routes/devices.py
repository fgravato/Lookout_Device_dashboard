"""
Device-related routes.
"""

import logging
from flask import Blueprint, jsonify, render_template, request, g, current_app
from flask_limiter import Limiter

from auth import AuthManager, require_auth
from services.risk_service import RiskService
from utils.device_filters import apply_device_filters
from utils.time_utils import days_since_checkin, get_connection_status

logger = logging.getLogger(__name__)
bp = Blueprint('devices', __name__)
limiter = None


def init_auth(manager: AuthManager, lim: Limiter):
    """Initialize auth manager and limiter"""
    global limiter
    limiter = lim


@bp.route('/')
@require_auth
def index():
    """Render the main dashboard page"""
    return render_template('index.html')


@bp.route('/api/devices')
@require_auth
def get_devices():
    """Get devices with caching support and enhanced data mapping"""
    try:
        device_service = current_app.extensions['device_service']
        device_cache = current_app.extensions['device_cache']
        config_class = current_app.extensions['config_class']
        
        allowed_params = ['force_refresh', 'platform', 'risk_level', 'days_since_checkin', 'days',
                          'search', 'os_version', 'mdm_identifier', 'tenant_id', 'mdm_provider']
        for param in request.args:
            if param not in allowed_params:
                return jsonify({'error': {'code': 'INVALID_PARAMETER', 'message': f'Invalid parameter: {param}'}}), 400

        force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
        cache_max_age = config_class.CACHE_MAX_AGE_MINUTES

        if not force_refresh:
            devices = device_service.get_cached_devices(cache_max_age)
            if devices is None:
                logger.info("Cache miss - fetching fresh device data")
                devices = device_service.fetch_and_cache_devices()
        else:
            logger.info("Force refresh requested")
            devices = device_service.fetch_and_cache_devices()

        filtered_devices = apply_device_filters(devices, request.args, RiskService.analyze_device_risk)
        cache_stats = device_service.get_cache_stats()

        return jsonify({
            'devices': filtered_devices,
            'total_count': len(filtered_devices),
            'cache_info': {
                'last_updated': cache_stats.get('last_sync_time'),
                'cache_age_minutes': cache_stats.get('cache_age_minutes'),
                'api_response_time': cache_stats.get('api_response_time'),
                'served_from_cache': not force_refresh and device_cache.is_valid(cache_max_age)
            }
        })

    except Exception as e:
        logger.error(f"Unexpected error in get_devices: {e}", exc_info=True)
        return jsonify({'error': {'code': 'DEVICE_FETCH_FAILED', 'message': 'Failed to fetch devices'}}), 500


@bp.route('/api/devices/groups')
@require_auth
def get_device_groups():
    """Get devices grouped by risk factors"""
    try:
        device_service = current_app.extensions['device_service']
        config_class = current_app.extensions['config_class']
        
        cache_max_age = config_class.CACHE_MAX_AGE_MINUTES
        devices = device_service.get_cached_devices(cache_max_age)
        
        if devices is None:
            logger.info("Cache miss - fetching fresh device data for grouping")
            devices = device_service.fetch_and_cache_devices()
        
        group_definitions = {
            'high_risk': {'name': 'High / Critical Risk', 'severity': 'high'},
            'medium_risk': {'name': 'Medium Risk', 'severity': 'medium'},
            'low_risk': {'name': 'Low Risk', 'severity': 'low'},
            'secure': {'name': 'Secure', 'severity': 'low'},
            'never_connected': {'name': 'Never Connected', 'severity': 'medium'},
            'stale': {'name': 'Stale (30+ days)', 'severity': 'medium'},
        }

        groups = {
            key: {'name': meta['name'], 'severity': meta['severity'], 'devices': []}
            for key, meta in group_definitions.items()
        }

        for device in devices:
            risk_level = device.get('risk_level', 'Unknown')
            days_since = device.get('days_since_checkin', -1)

            if days_since == -1:
                groups['never_connected']['devices'].append(device)
            elif days_since > 30:
                groups['stale']['devices'].append(device)

            if risk_level == 'Critical' or risk_level == 'High':
                groups['high_risk']['devices'].append(device)
            elif risk_level == 'Medium':
                groups['medium_risk']['devices'].append(device)
            elif risk_level == 'Low':
                groups['low_risk']['devices'].append(device)
            elif risk_level == 'Secure':
                groups['secure']['devices'].append(device)

        # Remove empty groups
        groups = {k: v for k, v in groups.items() if v['devices']}

        return jsonify({
            'groups': groups,
            'counts': {k: len(v['devices']) for k, v in groups.items()},
            'total_devices': len(devices)
        })
        
    except Exception as e:
        logger.error(f"Failed to group devices: {e}", exc_info=True)
        return jsonify({'error': {'code': 'GROUPING_FAILED', 'message': str(e)}}), 500


@bp.route('/api/vulnerabilities/<cve_name>')
@require_auth
def get_vulnerability_devices(cve_name):
    """Get devices affected by a specific CVE"""
    try:
        device_service = current_app.extensions['device_service']
        config_class = current_app.extensions['config_class']
        
        cache_max_age = config_class.CACHE_MAX_AGE_MINUTES
        devices = device_service.get_cached_devices(cache_max_age)
        
        if devices is None:
            devices = device_service.fetch_and_cache_devices()
        
        affected_devices = []
        for device in devices:
            device_cves = device.get('cves', [])
            if cve_name in device_cves:
                affected_devices.append(device)
        
        return jsonify({
            'cve_name': cve_name,
            'affected_devices': affected_devices,
            'affected_count': len(affected_devices)
        })
        
    except Exception as e:
        logger.error(f"Failed to get vulnerability devices: {e}", exc_info=True)
        return jsonify({'error': {'code': 'VULNERABILITY_FETCH_FAILED', 'message': str(e)}}), 500


@bp.route('/api/device/<device_id>')
@require_auth
def get_device_details(device_id):
    """Get detailed information for a specific device"""
    try:
        device_service = current_app.extensions['device_service']
        config_class = current_app.extensions['config_class']
        
        cache_max_age = config_class.CACHE_MAX_AGE_MINUTES
        devices = device_service.get_cached_devices(cache_max_age)
        
        if devices is None:
            devices = device_service.fetch_and_cache_devices()
        
        device = None
        for d in devices:
            if d.get('device_id') == device_id:
                device = d
                break
        
        if not device:
            return jsonify({'error': {'code': 'DEVICE_NOT_FOUND', 'message': f'Device {device_id} not found'}}), 404
        
        risk_analysis = RiskService.analyze_device_risk(device)
        
        return jsonify({
            'device': device,
            'risk_analysis': risk_analysis
        })
        
    except Exception as e:
        logger.error(f"Failed to get device details: {e}", exc_info=True)
        return jsonify({'error': {'code': 'DEVICE_DETAILS_FAILED', 'message': str(e)}}), 500
