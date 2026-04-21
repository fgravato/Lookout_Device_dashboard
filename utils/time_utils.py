"""
Time and Status Utilities

Canonical source for all time-based calculations and connection status logic.
Consolidates duplicated logic from device_filters, risk_service, device_service, and export_service.
"""

from datetime import datetime
from typing import Dict, Any, Optional


def parse_checkin_time(checkin_str: Optional[str]) -> Optional[datetime]:
    """
    Parse a checkin time string to a datetime object.
    
    Args:
        checkin_str: ISO datetime string (e.g., "2024-01-15T10:30:00Z") or 'Never'
        
    Returns:
        datetime object with timezone info, or None if invalid/never connected
    """
    if not checkin_str or checkin_str == 'Never':
        return None
    
    try:
        return datetime.fromisoformat(checkin_str.replace('Z', '+00:00'))
    except (ValueError, TypeError, AttributeError):
        return None


def days_since_checkin(checkin_str: Optional[str]) -> int:
    """
    Calculate the number of days since the last checkin.
    
    Args:
        checkin_str: ISO datetime string or 'Never'
        
    Returns:
        Number of days since checkin, or -1 if never connected or invalid
    """
    last_checkin = parse_checkin_time(checkin_str)
    if last_checkin is None:
        return -1
    
    try:
        now = datetime.now().replace(tzinfo=last_checkin.tzinfo)
        return (now - last_checkin).days
    except (ValueError, TypeError):
        return -1


def get_connection_status(days_since: int) -> Dict[str, Any]:
    """
    Get connection status information based on days since last checkin.
    
    Args:
        days_since: Number of days since last checkin, -1 for never connected
        
    Returns:
        Dictionary with status info:
            - status: Machine-readable status key
            - label: Human-readable label
            - color: Hex color code
            - severity: Bootstrap severity class (success, info, warning, danger, secondary)
            - icon: FontAwesome icon name
    """
    if days_since < 0:
        return {
            'status': 'never_connected',
            'label': 'Never Connected',
            'color': '#6c757d',
            'severity': 'secondary',
            'icon': 'question-circle'
        }
    elif days_since <= 1:
        return {
            'status': 'connected',
            'label': 'Connected',
            'color': '#28a745',
            'severity': 'success',
            'icon': 'check-circle'
        }
    elif days_since <= 7:
        return {
            'status': 'recent',
            'label': 'Recent',
            'color': '#17a2b8',
            'severity': 'info',
            'icon': 'info-circle'
        }
    elif days_since <= 30:
        return {
            'status': 'stale',
            'label': 'Stale',
            'color': '#ffc107',
            'severity': 'warning',
            'icon': 'exclamation-triangle'
        }
    elif days_since <= 90:
        return {
            'status': 'disconnected',
            'label': 'Disconnected',
            'color': '#fd7e14',
            'severity': 'warning',
            'icon': 'exclamation-triangle'
        }
    else:
        return {
            'status': 'very_stale',
            'label': 'Very Stale',
            'color': '#dc3545',
            'severity': 'danger',
            'icon': 'times-circle'
        }


def matches_connection_filter(days_since: int, filter_type: str) -> bool:
    """
    Check if a device's days since checkin matches a connection filter preset.
    
    Args:
        days_since: Number of days since last checkin, -1 for never connected
        filter_type: Filter preset name:
            - 'connected': <= 1 day
            - 'recent': 2-7 days
            - 'stale': 8-30 days
            - 'disconnected': 31-90 days
            - 'very_stale': > 90 days
            - 'never_connected': Never connected (-1)
            - '' or None: No filter (always matches)
            
    Returns:
        True if device matches the filter, False otherwise
    """
    if not filter_type:
        return True
    
    if days_since < 0:
        return filter_type == 'never_connected'
    
    if filter_type == 'connected':
        return days_since <= 1
    elif filter_type == 'recent':
        return 2 <= days_since <= 7
    elif filter_type == 'stale':
        return 8 <= days_since <= 30
    elif filter_type == 'disconnected':
        return 31 <= days_since <= 90
    elif filter_type == 'very_stale':
        return days_since > 90
    elif filter_type == 'never_connected':
        return False  # Already handled above for days_since < 0
    
    return True  # Unknown filter type, allow all


def days_since_checkin_from_device(device: Dict[str, Any]) -> int:
    """
    Convenience function to calculate days since checkin from a device dictionary.
    
    Looks for 'checkin_time' or 'last_checkin' fields.
    
    Args:
        device: Device dictionary
        
    Returns:
        Number of days since checkin, or -1 if never connected or invalid
    """
    checkin_str = device.get('checkin_time') or device.get('last_checkin')
    return days_since_checkin(checkin_str)
