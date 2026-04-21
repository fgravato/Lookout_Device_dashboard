"""
Device Filtering Utilities

Centralized filtering logic for device data used across multiple endpoints.
"""

import logging
from typing import List, Dict, Any, Optional, Callable

from utils.time_utils import days_since_checkin, get_connection_status, matches_connection_filter

logger = logging.getLogger(__name__)


def apply_device_filters(devices: List[Dict], filter_args: Dict[str, Any], 
                        risk_analyzer_func: Optional[Callable] = None) -> List[Dict]:
    """
    Apply filtering logic to device list
    
    Args:
        devices: List of device dictionaries
        filter_args: Dictionary of filter parameters (supports multi-tenant filtering)
        risk_analyzer_func: Function to analyze device risk (optional)
        
    Returns:
        List of filtered and formatted devices
    """
    # Get query parameters
    connection_filter = filter_args.get('days')  # Connection status presets
    platform_filter = filter_args.get('platform')
    risk_level_filter = filter_args.get('risk_level')
    os_version_filter = filter_args.get('os_version', '').lower()
    search_term = filter_args.get('search', '').lower()
    
    # Multi-tenant filters
    mdm_identifier_filter = filter_args.get('mdm_identifier')
    tenant_id_filter = filter_args.get('tenant_id')
    mdm_provider_filter = filter_args.get('mdm_provider')
    
    filtered_devices = []
    
    for device in devices:
        # Skip if device doesn't have required fields
        required_fields = ['device_name', 'platform', 'risk_level']
        checkin_field = device.get('checkin_time') or device.get('last_checkin')
        if not all(key in device for key in required_fields):
            continue

        # Only support iOS and Android platforms
        platform = device.get('platform', '').lower()
        if platform not in ['ios', 'android']:
            continue

        # Use pre-computed days_since_checkin if available, otherwise calculate
        days_since = device.get('days_since_checkin')
        if days_since is None:
            days_since = days_since_checkin(checkin_field)

        # Apply connection status filter
        if connection_filter and not matches_connection_filter(days_since, connection_filter):
            continue
        
        # Apply platform filter
        if platform_filter and device.get('platform', '').lower() != platform_filter.lower():
            continue

        # Apply risk level filter
        if risk_level_filter and device.get('risk_level', '').lower() != risk_level_filter.lower():
            continue
        
        # Apply multi-tenant filters
        if mdm_identifier_filter and device.get('mdm_identifier') != mdm_identifier_filter:
            continue
        
        if tenant_id_filter and device.get('tenant_id') != tenant_id_filter:
            continue
        
        if mdm_provider_filter and device.get('mdm_provider', '').lower() != mdm_provider_filter.lower():
            continue

        # Apply OS version filter
        if os_version_filter:
            device_os_version = device.get('os_version', '').lower()
            if os_version_filter not in device_os_version:
                continue

        # Apply search filter
        if search_term:
            searchable_text = f"{device.get('device_name', '')} {device.get('user_email', '')} {device.get('device_id', '')}".lower()
            if search_term not in searchable_text:
                continue

        # Use pre-computed risk_analysis if available, otherwise calculate
        active_issues_count = 0
        if 'risk_analysis' in device and device['risk_analysis']:
            active_issues_count = device['risk_analysis'].get('total_issues', 0)
        elif risk_analyzer_func:
            try:
                risk_analysis = risk_analyzer_func(device)
                active_issues_count = risk_analysis.get('total_issues', 0)
            except Exception as e:
                logger.warning(f"Error analyzing device risk: {e}")

        # Use pre-computed connection_status_info if available, otherwise calculate
        connection_status_info = device.get('connection_status_info')
        if connection_status_info is None:
            connection_status_info = get_connection_status(days_since)

        # Format device data for response
        formatted_device = {
            'device_name': device.get('device_name', 'Unknown'),
            'device_id': device.get('device_id', ''),
            'user_email': device.get('user_email', 'N/A'),
            'platform': device.get('platform', 'Unknown'),
            'risk_level': device.get('risk_level', 'Unknown'),
            'last_checkin': checkin_field or 'Never',
            'os_version': device.get('os_version', 'Unknown'),
            'app_version': device.get('app_version', 'Unknown'),
            'compliance_status': device.get('compliance_status', 'Unknown'),
            # Enhanced fields from new mapping
            'security_patch_level': device.get('security_patch_level'),
            'manufacturer': device.get('manufacturer'),
            'model': device.get('model'),
            'activation_status': device.get('activation_status'),
            # Active issues count
            'active_issues_count': active_issues_count,
            # Connection status info
            'days_since_checkin': days_since,
            'connection_status_info': connection_status_info,
            # MDM information from API
            'mdm_connector_id': device.get('mdm_connector_id'),
            'mdm_connector_uuid': device.get('mdm_connector_uuid'),
            'external_id': device.get('external_id'),
            # Multi-tenant fields
            'mdm_identifier': device.get('mdm_identifier'),
            'mdm_provider': device.get('mdm_provider'),
            'tenant_id': device.get('tenant_id'),
            'tenant_name': device.get('tenant_name')
        }

        filtered_devices.append(formatted_device)
    
    return filtered_devices


def filter_devices_for_export(devices: List[Dict], filter_args: Dict[str, Any]) -> List[Dict]:
    """
    Apply filtering for export functionality (lighter version without formatting)
    
    Args:
        devices: List of device dictionaries
        filter_args: Dictionary of filter parameters
        
    Returns:
        List of filtered devices (original format)
    """
    connection_filter = filter_args.get('days')
    platform_filter = filter_args.get('platform')
    risk_level_filter = filter_args.get('risk_level')
    os_version_filter = filter_args.get('os_version', '').lower()
    search_term = filter_args.get('search', '').lower()
    
    filtered_devices = []
    
    for device in devices:
        has_checkin = 'last_checkin' in device or 'checkin_time' in device
        if not all(key in device for key in ['device_name', 'platform', 'risk_level']) or not has_checkin:
            continue

        # Only support iOS and Android platforms
        platform = device.get('platform', '').lower()
        if platform not in ['ios', 'android']:
            continue

        # Use pre-computed days_since_checkin if available, otherwise calculate
        checkin_field = device.get('last_checkin') or device.get('checkin_time')
        days_since = device.get('days_since_checkin')
        if days_since is None:
            days_since = days_since_checkin(checkin_field)

        # Apply connection status filter
        if connection_filter and not matches_connection_filter(days_since, connection_filter):
            continue

        # Apply platform filter
        if platform_filter and device.get('platform', '').lower() != platform_filter.lower():
            continue

        # Apply risk level filter
        if risk_level_filter and device.get('risk_level', '').lower() != risk_level_filter.lower():
            continue

        # Apply OS version filter
        if os_version_filter:
            device_os_version = device.get('os_version', '').lower()
            if os_version_filter not in device_os_version:
                continue

        # Apply search filter
        if search_term:
            searchable_text = f"{device.get('device_name', '')} {device.get('user_email', '')} {device.get('device_id', '')}".lower()
            if search_term not in searchable_text:
                continue

        filtered_devices.append(device)

    return filtered_devices
