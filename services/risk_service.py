"""
Risk Analysis Service

Handles all device risk assessment and analysis logic.
"""

import logging
from typing import Dict, List, Any

from utils.time_utils import days_since_checkin_from_device

logger = logging.getLogger(__name__)


class RiskService:
    """Service for analyzing device risk factors and providing recommendations"""
    
    @staticmethod
    def analyze_device_risk(device: Dict) -> Dict[str, Any]:
        """
        Analyze device risk factors and provide explanations
        
        Args:
            device: Device dictionary with all available fields
            
        Returns:
            Dictionary containing risk analysis results
        """
        risk_factors = []
        recommendations = []
        
        # Check for actual security threats first (this is the primary risk driver)
        security_status = device.get('security_status', '')
        if security_status in ['THREATS_HIGH', 'CRITICAL']:
            risk_factors.append({
                'category': 'Security Threats',
                'issue': 'Active Security Threats Detected',
                'description': 'Lookout has detected high-severity security threats on this device',
                'severity': 'Critical' if security_status == 'CRITICAL' else 'High',
                'impact': 'Device is actively compromised or at immediate risk of compromise'
            })
            recommendations.append('Immediately investigate and remediate detected threats')
            recommendations.append('Consider isolating device until threats are resolved')
        elif security_status == 'THREATS_MEDIUM':
            risk_factors.append({
                'category': 'Security Threats',
                'issue': 'Moderate Security Threats Detected',
                'description': 'Lookout has detected moderate security threats on this device',
                'severity': 'Medium',
                'impact': 'Device has security concerns that should be addressed promptly'
            })
            recommendations.append('Investigate and remediate detected threats')
        elif security_status == 'THREATS_LOW':
            risk_factors.append({
                'category': 'Security Threats',
                'issue': 'Minor Security Concerns Detected',
                'description': 'Lookout has detected low-level security concerns on this device',
                'severity': 'Low',
                'impact': 'Device has minor security issues that should be monitored'
            })
            recommendations.append('Review and address detected security concerns')
        
        # Check OS version status (but only flag if device is not already secure)
        # If device is marked as SECURE, the current OS version meets policy requirements
        os_version = device.get('os_version', '')
        latest_os = device.get('latest_os_version', '')
        if (os_version and latest_os and os_version != latest_os and
            security_status not in ['SECURE']):
            risk_factors.append({
                'category': 'Operating System',
                'issue': 'Outdated OS Version',
                'description': f'Device is running {os_version}, but {latest_os} is available',
                'severity': 'Medium',
                'impact': 'Security vulnerabilities may be present'
            })
            recommendations.append('Update to the latest OS version')
        
        # Check security patch level (but only flag if device is not already secure)
        # If device is marked as SECURE, the current patch level meets policy requirements
        patch_level = device.get('security_patch_level', '')
        latest_patch = device.get('latest_security_patch_level', '')
        if (patch_level and latest_patch and patch_level != latest_patch and
            security_status not in ['SECURE']):
            risk_factors.append({
                'category': 'Security Patches',
                'issue': 'Missing Security Patches',
                'description': f'Security patch level: {patch_level}, Latest: {latest_patch}',
                'severity': 'High',
                'impact': 'Device vulnerable to known security exploits'
            })
            recommendations.append('Install latest security patches')
        
        # Check last checkin time
        days_since = RiskService.calculate_days_since_checkin(device)
        if days_since > 30:
            risk_factors.append({
                'category': 'Device Management',
                'issue': 'Infrequent Check-ins',
                'description': f'Device has not checked in for {days_since} days',
                'severity': 'Medium',
                'impact': 'Device may be lost, stolen, or have connectivity issues'
            })
            recommendations.append('Investigate device connectivity and user status')
        elif days_since > 7:
            risk_factors.append({
                'category': 'Device Management',
                'issue': 'Delayed Check-ins',
                'description': f'Device has not checked in for {days_since} days',
                'severity': 'Low',
                'impact': 'Monitoring and policy enforcement may be delayed'
            })
            recommendations.append('Verify device connectivity')
        
        # Check protection status
        protection_status = device.get('protection_status', '')
        if protection_status in ['DISCONNECTED', 'UNPROTECTED']:
            risk_factors.append({
                'category': 'Protection Status',
                'issue': 'Device Not Protected',
                'description': f'Protection status: {protection_status}',
                'severity': 'Critical',
                'impact': 'Device is not receiving security protection'
            })
            recommendations.append('Reinstall or reconfigure security agent')
        
        # Check activation status
        activation_status = device.get('activation_status', '')
        if activation_status != 'ACTIVATED':
            risk_factors.append({
                'category': 'Activation',
                'issue': 'Device Not Properly Activated',
                'description': f'Activation status: {activation_status}',
                'severity': 'High',
                'impact': 'Device may not be fully managed or protected'
            })
            recommendations.append('Complete device activation process')
        
        # Determine overall risk explanation
        risk_explanation = RiskService.get_risk_explanation(security_status, len(risk_factors))
        
        return {
            'risk_factors': risk_factors,
            'recommendations': recommendations,
            'risk_explanation': risk_explanation,
            'total_issues': len(risk_factors)
        }
    
    @staticmethod
    def calculate_days_since_checkin(device: Dict) -> int:
        """Calculate days since last checkin"""
        return days_since_checkin_from_device(device)
    
    @staticmethod
    def get_risk_explanation(security_status: str, issue_count: int) -> str:
        """
        Get explanation for device risk level
        
        Args:
            security_status: Device security status from Lookout
            issue_count: Number of configuration/maintenance issues
            
        Returns:
            Human-readable risk explanation
        """
        explanations = {
            'SECURE': 'Device is secure with no known threats detected.',
            'THREATS_LOW': 'Device has minor security concerns that should be addressed.',
            'THREATS_MEDIUM': 'Device has moderate security risks requiring attention.',
            'THREATS_HIGH': 'Device has significant security threats that need immediate action.',
            'CRITICAL': 'Device has critical security issues requiring urgent intervention.'
        }
        
        base_explanation = explanations.get(security_status, 'Security status unknown.')
        
        if issue_count > 0:
            base_explanation += f' {issue_count} configuration or maintenance issue(s) detected.'
        
        return base_explanation

    @staticmethod
    def group_devices_by_risk(devices: List[Dict]) -> Dict[str, Any]:
        """
        Group devices by risk level and connection status

        Args:
            devices: List of device dictionaries

        Returns:
            Dictionary with groups, per-group counts, and total device count
        """
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

        return {
            'groups': groups,
            'counts': {k: len(v['devices']) for k, v in groups.items()},
            'total_devices': len(devices)
        }