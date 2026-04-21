"""
Risk Analysis Service

Handles all device risk assessment and analysis logic.
"""

import logging
from typing import Dict, List, Any, Optional

from utils.time_utils import days_since_checkin_from_device, matches_connection_filter

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
    def get_device_details(device: Dict) -> Dict[str, Any]:
        """
        Prepare detailed device information with risk analysis
        
        Args:
            device: Raw device dictionary
            
        Returns:
            Formatted device details with risk analysis
        """
        # Calculate risk factors and analysis
        risk_analysis = RiskService.analyze_device_risk(device)
        
        # Prepare detailed device information
        device_details = {
            'basic_info': {
                'device_name': device.get('device_name', 'Unknown'),
                'device_id': device.get('device_id', ''),
                'user_email': device.get('user_email', 'N/A'),
                'platform': device.get('platform', 'Unknown'),
                'manufacturer': device.get('manufacturer', 'Unknown'),
                'model': device.get('model', 'Unknown'),
                'activation_status': device.get('activation_status', 'Unknown')
            },
             'security_status': {
                 'risk_level': device.get('risk_level', 'Unknown'),
                 'security_status': device.get('security_status', 'Unknown'),
                 'protection_status': device.get('protection_status', 'Unknown'),
                 'compliance_status': device.get('compliance_status', 'Unknown')  # Or use custom logic here
             },
            'software_info': {
                'os_version': device.get('os_version', 'Unknown'),
                'security_patch_level': device.get('security_patch_level', 'Unknown'),
                'latest_os_version': device.get('latest_os_version', 'Unknown'),
                'latest_security_patch_level': device.get('latest_security_patch_level', 'Unknown'),
                'app_version': device.get('app_version', 'Unknown'),
                'sdk_version': device.get('sdk_version', 'Unknown'),
                'rsr': device.get('rsr', 'Unknown')
            },
            'timing_info': {
                'last_checkin': device.get('checkin_time') or device.get('last_checkin'),
                'activated_at': device.get('activated_at'),
                'updated_time': device.get('updated_time'),
                'days_since_checkin': RiskService.calculate_days_since_checkin(device)
            },
            'risk_analysis': risk_analysis
        }
        
        return device_details

    @staticmethod
    def group_devices_by_issues(devices: List[Dict], connection_filter: Optional[str] = None, risk_level_filter: Optional[str] = None, platform_filter: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Group devices by common issues and connection status

        Args:
            devices: List of device dictionaries
            connection_filter: Optional connection status filter ('connected', 'recent', etc.)

        Returns:
            Dictionary with issue groups as keys and lists of devices as values
        """
        issue_groups = {
            'outdated_os': {'name': 'Outdated OS Version', 'devices': [], 'severity': 'Medium'},
            'missing_patches': {'name': 'Missing Security Patches', 'devices': [], 'severity': 'High'},
            'security_threats': {'name': 'Active Security Threats', 'devices': [], 'severity': 'Critical'},
            'protection_issues': {'name': 'Protection Issues', 'devices': [], 'severity': 'Critical'},
            'activation_issues': {'name': 'Activation Issues', 'devices': [], 'severity': 'High'},
            'checkin_issues': {'name': 'Check-in Issues', 'devices': [], 'severity': 'Medium'},
            'secure_devices': {'name': 'Secure Devices', 'devices': [], 'severity': 'Low'}
        }

        for device in devices:
            # Apply connection filter if specified
            if connection_filter:
                days_since = RiskService.calculate_days_since_checkin(device)
                if not RiskService._matches_connection_filter(days_since, connection_filter):
                    continue

            # Apply risk level filter if specified
            if risk_level_filter and device.get('risk_level', '').lower() != risk_level_filter.lower():
                continue

            # Apply platform filter if specified
            if platform_filter and device.get('platform', '').lower() != platform_filter.lower():
                continue

            # Analyze device risks
            risk_analysis = RiskService.analyze_device_risk(device)
            risk_factors = risk_analysis.get('risk_factors', [])

            # Determine primary issue category
            primary_issue = None
            security_status = device.get('security_status', '')

            # Check for security threats first (highest priority)
            if security_status in ['THREATS_HIGH', 'CRITICAL', 'THREATS_MEDIUM']:
                primary_issue = 'security_threats'
            # Check for protection issues
            elif device.get('protection_status') in ['DISCONNECTED', 'UNPROTECTED']:
                primary_issue = 'protection_issues'
            # Check for activation issues
            elif device.get('activation_status') != 'ACTIVATED':
                primary_issue = 'activation_issues'
            # Check for outdated OS
            elif any(factor.get('issue') == 'Outdated OS Version' for factor in risk_factors):
                primary_issue = 'outdated_os'
            # Check for missing patches
            elif any(factor.get('issue') == 'Missing Security Patches' for factor in risk_factors):
                primary_issue = 'missing_patches'
            # Check for check-in issues
            elif any(factor.get('issue') in ['Infrequent Check-ins', 'Delayed Check-ins'] for factor in risk_factors):
                primary_issue = 'checkin_issues'
            # If no issues found, it's secure
            elif security_status == 'SECURE' and not risk_factors:
                primary_issue = 'secure_devices'

            # Add device to appropriate group
            if primary_issue and primary_issue in issue_groups:
                issue_groups[primary_issue]['devices'].append(device)

        # Remove empty groups
        return {k: v for k, v in issue_groups.items() if v['devices']}

    @staticmethod
    def _matches_connection_filter(days_since: int, filter_type: str) -> bool:
        """Helper method to check if device matches connection filter"""
        return matches_connection_filter(days_since, filter_type)