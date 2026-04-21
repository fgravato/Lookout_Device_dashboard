"""
CVE scanner routes.
"""

import logging
import os
import re
from datetime import datetime
from flask import Blueprint, jsonify, request, send_file, after_this_request, g, current_app
from flask_limiter import Limiter

from auth import AuthManager, require_auth
from services.cve_service import CVEService
from services.risk_service import RiskService
from utils.time_utils import days_since_checkin

logger = logging.getLogger(__name__)
bp = Blueprint('cve', __name__)
limiter = None


def init_auth(manager: AuthManager, lim: Limiter):
    """Initialize auth manager and limiter"""
    global limiter
    limiter = lim


_CVE_PATTERN = re.compile(r'^CVE-\d{4}-\d+$', re.IGNORECASE)


def _validate_cve_name(cve_name: str) -> bool:
    """Return True if cve_name matches the standard CVE-YYYY-NNNNN format."""
    return bool(_CVE_PATTERN.match(cve_name))


def _severity_label(severity: float) -> str:
    """Convert numeric severity to label"""
    if severity >= 9:
        return 'Critical'
    elif severity >= 7:
        return 'High'
    elif severity >= 4:
        return 'Medium'
    return 'Low'


def get_cve_service():
    """Get or create CVE service"""
    cve_service = current_app.extensions.get('cve_service')
    if cve_service is None:
        device_service = current_app.extensions['device_service']
        client = device_service.get_lookout_client()
        if client:
            cve_service = CVEService(client)
            current_app.extensions['cve_service'] = cve_service
    return cve_service


@bp.route('/cve/scan')
@require_auth
def scan_fleet_cves():
    """Scan fleet for CVE vulnerabilities"""
    try:
        device_service = current_app.extensions['device_service']
        config_class = current_app.extensions['config_class']
        
        min_severity = request.args.get('min_severity', 7, type=int)
        
        cache_max_age = config_class.CACHE_MAX_AGE_MINUTES
        devices = device_service.get_cached_devices(cache_max_age)
        
        if devices is None:
            devices = device_service.fetch_and_cache_devices()
        
        cve_service = get_cve_service()
        if not cve_service:
            return jsonify({'error': {'code': 'CVE_SERVICE_UNAVAILABLE', 'message': 'CVE service not available'}}), 503
        
        os_versions = cve_service.get_fleet_os_versions()
        
        all_vulnerabilities = []
        affected_devices = set()
        
        android_patches = set()
        ios_versions = set()
        
        for device in devices:
            platform = device.get('platform', '').lower()
            
            if platform == 'android':
                patch_level = device.get('security_patch_level', '')
                if patch_level:
                    android_patches.add(patch_level)
            elif platform == 'ios':
                os_version = device.get('os_version', '')
                if os_version:
                    ios_versions.add(os_version)
        
        # Index devices by patch/version for efficient lookup
        devices_by_android_patch = {}
        devices_by_ios_version = {}
        for device in devices:
            platform = device.get('platform', '').lower()
            if platform == 'android':
                pl = device.get('security_patch_level', '')
                if pl:
                    devices_by_android_patch.setdefault(pl, []).append(device)
            elif platform == 'ios':
                ov = device.get('os_version', '')
                if ov:
                    devices_by_ios_version.setdefault(ov, []).append(device)

        cve_device_map = {}  # cve_id -> set of device_ids

        for patch in android_patches:
            vulns = cve_service.get_vulnerabilities_for_android_patch(patch, min_severity)
            patch_devices = devices_by_android_patch.get(patch, [])
            for vuln_wrapper in vulns:
                # Unwrap nested vulnerability object
                vuln = vuln_wrapper.get('vulnerability', vuln_wrapper) if isinstance(vuln_wrapper, dict) else vuln_wrapper
                cve_id = vuln.get('name') or vuln.get('cve') or vuln.get('cve_id') or 'Unknown'
                severity = float(vuln.get('severity', 0) or 0)

                all_vulnerabilities.append({
                    'cve': cve_id,
                    'severity': severity,
                    'severity_label': _severity_label(severity),
                    'description': vuln.get('description', ''),
                    'summary': vuln.get('summary', ''),
                    'category': vuln.get('category', ''),
                    'classification': vuln.get('classification', ''),
                    'platform': 'Android',
                    'patch_level': patch,
                    'affected_device_count': len(patch_devices)
                })

                if cve_id not in cve_device_map:
                    cve_device_map[cve_id] = set()
                for d in patch_devices:
                    did = d.get('device_id')
                    if did:
                        cve_device_map[cve_id].add(did)
                        affected_devices.add(did)

        for version in ios_versions:
            vulns = cve_service.get_vulnerabilities_for_ios_version(version, min_severity)
            ver_devices = devices_by_ios_version.get(version, [])
            for vuln_wrapper in vulns:
                # Unwrap nested vulnerability object
                vuln = vuln_wrapper.get('vulnerability', vuln_wrapper) if isinstance(vuln_wrapper, dict) else vuln_wrapper
                cve_id = vuln.get('name') or vuln.get('cve') or vuln.get('cve_id') or 'Unknown'
                severity = float(vuln.get('severity', 0) or 0)

                all_vulnerabilities.append({
                    'cve': cve_id,
                    'severity': severity,
                    'severity_label': _severity_label(severity),
                    'description': vuln.get('description', ''),
                    'summary': vuln.get('summary', ''),
                    'category': vuln.get('category', ''),
                    'classification': vuln.get('classification', ''),
                    'platform': 'iOS',
                    'os_version': version,
                    'affected_device_count': len(ver_devices)
                })

                if cve_id not in cve_device_map:
                    cve_device_map[cve_id] = set()
                for d in ver_devices:
                    did = d.get('device_id')
                    if did:
                        cve_device_map[cve_id].add(did)
                        affected_devices.add(did)

        severity_counts = {'Critical': 0, 'High': 0, 'Medium': 0, 'Low': 0}
        for vuln in all_vulnerabilities:
            severity = vuln.get('severity', 0)
            if severity >= 9:
                severity_counts['Critical'] += 1
            elif severity >= 7:
                severity_counts['High'] += 1
            elif severity >= 4:
                severity_counts['Medium'] += 1
            else:
                severity_counts['Low'] += 1

        # Deduplicate CVEs and count unique affected devices per CVE
        cve_summary = {}
        for vuln in all_vulnerabilities:
            cve_id = vuln['cve']
            if cve_id not in cve_summary:
                cve_summary[cve_id] = {
                    'severity': vuln['severity'],
                    'device_ids': cve_device_map.get(cve_id, set())
                }
            else:
                cve_summary[cve_id]['device_ids'].update(cve_device_map.get(cve_id, set()))

        top_cves = sorted(
            [{'cve': cve_id, 'affected_devices': len(data['device_ids']), 'severity': data['severity']}
             for cve_id, data in cve_summary.items()],
            key=lambda x: (x['severity'], x['affected_devices']),
            reverse=True
        )[:10]

        unique_cve_count = len(cve_summary)

        return jsonify({
            'summary': {
                'total_devices': len(devices),
                'devices_with_vulnerabilities': len(affected_devices),
                'vulnerability_percentage': round(len(affected_devices) / len(devices) * 100, 1) if devices else 0,
                'total_cves_found': unique_cve_count,
                'severity_breakdown': severity_counts
            },
            'top_cves': top_cves,
            'all_vulnerabilities': all_vulnerabilities,
            'scan_metadata': {
                'android_patches_scanned': len(android_patches),
                'ios_versions_scanned': len(ios_versions),
                'minimum_severity': min_severity,
                'scan_time': datetime.now().isoformat()
            }
        })
        
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
        
        cve_service = get_cve_service()
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
        devices = device_service.get_cached_devices(cache_max_age)
        
        if devices is None:
            devices = device_service.fetch_and_cache_devices()
        
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
        export_service = current_app.extensions['export_service']
        
        min_severity = request.args.get('min_severity', 7, type=int)
        
        scan_result = scan_fleet_cves()

        # scan_fleet_cves returns (Response, status_code) tuple
        if isinstance(scan_result, tuple):
            response_obj, status_code = scan_result
        else:
            response_obj = scan_result
            status_code = 200

        if status_code != 200:
            return response_obj, status_code

        cve_report = response_obj.get_json()
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
