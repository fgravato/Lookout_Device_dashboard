"""
CVE scanner routes.
"""

import logging
import os
import re
from datetime import datetime
from flask import Blueprint, jsonify, request, send_file, after_this_request, g, current_app

from auth import require_auth
from services.risk_service import RiskService
from utils.time_utils import days_since_checkin

logger = logging.getLogger(__name__)
bp = Blueprint('cve', __name__)


_CVE_PATTERN = re.compile(r'^CVE-\d{4}-\d+$', re.IGNORECASE)


def _validate_cve_name(cve_name: str) -> bool:
    """Return True if cve_name matches the standard CVE-YYYY-NNNNN format."""
    return bool(_CVE_PATTERN.match(cve_name))


@bp.route('/cve/scan')
@require_auth
def scan_fleet_cves():
    """Scan fleet for CVE vulnerabilities"""
    try:
        device_service = current_app.extensions['device_service']
        config_class = current_app.extensions['config_class']

        min_severity = request.args.get('min_severity', 7, type=int)

        cache_max_age = config_class.CACHE_MAX_AGE_MINUTES
        devices = device_service.get_or_refresh_devices(cache_max_age)

        cve_service = current_app.extensions['cve_service']
        if not cve_service:
            return jsonify({'error': {'code': 'CVE_SERVICE_UNAVAILABLE', 'message': 'CVE service not available'}}), 503

        report = cve_service.scan_fleet_vulnerabilities(devices, min_severity)

        return jsonify(report)

    except Exception as e:
        logger.error(f"CVE scan failed: {e}", exc_info=True)
        return jsonify({'error': {'code': 'CVE_SCAN_FAILED', 'message': str(e)}}), 500


@bp.route('/cve/<cve_name>')
@require_auth
def get_cve_details(cve_name):
    """Get details for a specific CVE"""
    try:
        if not _validate_cve_name(cve_name):
            return jsonify({'error': {'code': 'INVALID_CVE_FORMAT', 'message': 'Invalid CVE format. Expected: CVE-YYYY-NNNNN'}}), 400

        cve_service = current_app.extensions['cve_service']
        if not cve_service:
            return jsonify({'error': {'code': 'CVE_SERVICE_UNAVAILABLE', 'message': 'CVE service not available'}}), 503

        # Get CVE info and affected devices from the Lookout API
        cve_info = cve_service.get_cve_details(cve_name)
        api_devices = cve_service.get_devices_affected_by_cve(cve_name)

        # Enrich API devices with cached fleet data (names, emails, etc.)
        device_service = current_app.extensions['device_service']
        config_class = current_app.extensions['config_class']
        cached_devices = device_service.get_cached_devices(config_class.CACHE_MAX_AGE_MINUTES) or []

        # Build lookup by device_id (guid)
        cache_lookup = {}
        for d in cached_devices:
            did = d.get('device_id') or d.get('guid')
            if did:
                cache_lookup[did] = d

        enriched_devices = []
        for api_dev in api_devices:
            guid = api_dev.get('guid', '')
            cached = cache_lookup.get(guid, {})
            enriched_devices.append({
                'guid': guid,
                'device_name': cached.get('device_name') or cached.get('customer_device_id') or guid[:12],
                'email': cached.get('email') or cached.get('user_email') or 'N/A',
                'platform': cached.get('platform') or api_dev.get('platform', 'Unknown'),
                'os_version': cached.get('os_version') or api_dev.get('os_version', 'Unknown'),
                'security_patch_level': cached.get('security_patch_level') or 'N/A',
                'model': cached.get('hardware_model') or cached.get('model') or '',
                'last_checkin': cached.get('last_checkin') or '',
                'risk_level': cached.get('risk_posture') or cached.get('risk_level') or '',
            })

        return jsonify({
            'cve': cve_name,
            'cve_info': cve_info,
            'affected_devices': enriched_devices,
            'affected_devices_count': len(enriched_devices)
        })

    except Exception as e:
        logger.error(f"Failed to get CVE details: {e}", exc_info=True)
        return jsonify({'error': {'code': 'CVE_DETAILS_FAILED', 'message': str(e)}}), 500


@bp.route('/cve/fleet/os-versions')
@require_auth
def get_fleet_os_versions():
    """Get all OS versions in the fleet"""
    try:
        device_service = current_app.extensions['device_service']
        config_class = current_app.extensions['config_class']
        
        cache_max_age = config_class.CACHE_MAX_AGE_MINUTES
        devices = device_service.get_or_refresh_devices(cache_max_age)

        android_versions = {}
        ios_versions = {}
        
        for device in devices:
            platform = device.get('platform', '').lower()
            
            if platform == 'android':
                version = device.get('os_version', 'Unknown')
                android_versions[version] = android_versions.get(version, 0) + 1
            elif platform == 'ios':
                version = device.get('os_version', 'Unknown')
                ios_versions[version] = ios_versions.get(version, 0) + 1
        
        return jsonify({
            'android_versions': [{'version': v, 'count': c} for v, c in android_versions.items()],
            'ios_versions': [{'version': v, 'count': c} for v, c in ios_versions.items()],
            'total_devices': len(devices)
        })
        
    except Exception as e:
        logger.error(f"Failed to get fleet OS versions: {e}", exc_info=True)
        return jsonify({'error': {'code': 'OS_VERSIONS_FAILED', 'message': str(e)}}), 500


@bp.route('/cve/export/excel')
@require_auth
def export_cve_report():
    """Export CVE report to Excel"""
    try:
        device_service = current_app.extensions['device_service']
        export_service = current_app.extensions['export_service']
        config_class = current_app.extensions['config_class']

        min_severity = request.args.get('min_severity', 7, type=int)

        cve_service = current_app.extensions['cve_service']
        if not cve_service:
            return jsonify({'error': {'code': 'CVE_SERVICE_UNAVAILABLE', 'message': 'CVE service not available'}}), 503

        cache_max_age = config_class.CACHE_MAX_AGE_MINUTES
        devices = device_service.get_or_refresh_devices(cache_max_age)

        cve_report = cve_service.scan_fleet_vulnerabilities(devices, min_severity)
        filepath = export_service.export_cve_report_to_excel(cve_report)

        @after_this_request
        def _cleanup(response):
            try:
                os.remove(filepath)
            except OSError:
                pass
            return response

        return send_file(filepath, as_attachment=True, download_name=f"cve_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        
    except Exception as e:
        logger.error(f"CVE export failed: {e}", exc_info=True)
        return jsonify({'error': {'code': 'CVE_EXPORT_FAILED', 'message': str(e)}}), 500
