"""
CVE Vulnerability Service

Handles CVE vulnerability scanning and analysis for the device fleet.
"""

import logging
from typing import List, Dict, Any, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class CVEService:
    """Service for CVE vulnerability scanning and analysis"""
    
    def __init__(self, lookout_client):
        """
        Initialize CVE service
        
        Args:
            lookout_client: Authenticated Lookout API client
        """
        self.lookout_client = lookout_client
    
    def get_fleet_os_versions(self) -> Dict[str, Any]:
        """
        Get all OS versions present in the fleet
        
        Returns:
            Dictionary with Android and iOS versions
        """
        try:
            if not self.lookout_client.is_authenticated():
                self.lookout_client.authenticate()
            
            response = self.lookout_client.get_fleet_os_versions()
            logger.info("Retrieved OS versions for fleet")
            return response
            
        except Exception as e:
            logger.error(f"Failed to get fleet OS versions: {e}")
            return {'android_versions': [], 'ios_versions': []}
    
    def get_vulnerabilities_for_android_patch(self, aspl: str, min_severity: Optional[int] = None) -> List[Dict]:
        """
        Get CVE vulnerabilities for a specific Android Security Patch Level
        
        Args:
            aspl: Android Security Patch Level (e.g., "2024-01-01")
            min_severity: Minimum severity level (0-10), optional
            
        Returns:
            List of vulnerability dictionaries
        """
        try:
            if not self.lookout_client.is_authenticated():
                self.lookout_client.authenticate()
            
            vulns = self.lookout_client.get_android_vulnerabilities(aspl, min_severity)
            vulns_list = vulns.get('vulnerabilities', [])
            
            # Debug: Log first vulnerability structure if available
            if vulns_list and len(vulns_list) > 0:
                logger.debug(f"Sample Android vulnerability structure: {list(vulns_list[0].keys())}")
            
            logger.info(f"Found {len(vulns_list)} vulnerabilities for Android patch {aspl}")
            return vulns_list
            
        except Exception as e:
            logger.error(f"Failed to get Android vulnerabilities for {aspl}: {e}")
            return []
    
    def get_vulnerabilities_for_ios_version(self, version: str, min_severity: Optional[int] = None) -> List[Dict]:
        """
        Get CVE vulnerabilities for a specific iOS version
        
        Args:
            version: iOS version (e.g., "17.2.1")
            min_severity: Minimum severity level (0-10), optional
            
        Returns:
            List of vulnerability dictionaries
        """
        try:
            if not self.lookout_client.is_authenticated():
                self.lookout_client.authenticate()
            
            vulns = self.lookout_client.get_ios_vulnerabilities(version, min_severity)
            vulns_list = vulns.get('vulnerabilities', [])
            
            # Debug: Log first vulnerability structure if available
            if vulns_list and len(vulns_list) > 0:
                logger.debug(f"Sample iOS vulnerability structure: {list(vulns_list[0].keys())}")
            
            logger.info(f"Found {len(vulns_list)} vulnerabilities for iOS {version}")
            return vulns_list
            
        except Exception as e:
            logger.error(f"Failed to get iOS vulnerabilities for {version}: {e}")
            return []
    
    def get_cve_details(self, cve_name: str) -> Optional[Dict]:
        """
        Get detailed information about a specific CVE
        
        Args:
            cve_name: CVE identifier (e.g., "CVE-2024-12345")
            
        Returns:
            CVE details dictionary or None
        """
        try:
            if not self.lookout_client.is_authenticated():
                self.lookout_client.authenticate()
            
            cve_info = self.lookout_client.get_cve_info(cve_name)
            logger.info(f"Retrieved details for {cve_name}")
            return cve_info
            
        except Exception as e:
            logger.error(f"Failed to get CVE details for {cve_name}: {e}")
            return None
    
    def get_devices_affected_by_cve(self, cve_name: str) -> List[Dict]:
        """
        Get all devices in the fleet affected by a specific CVE
        
        Args:
            cve_name: CVE identifier (e.g., "CVE-2024-12345")
            
        Returns:
            List of affected device dictionaries
        """
        try:
            if not self.lookout_client.is_authenticated():
                self.lookout_client.authenticate()
            
            response = self.lookout_client.get_devices_by_cve(cve_name)
            devices = response.get('devices', [])
            logger.info(f"Found {len(devices)} devices affected by {cve_name}")
            return devices
            
        except Exception as e:
            logger.error(f"Failed to get devices for {cve_name}: {e}")
            return []
    
    def scan_fleet_vulnerabilities(self, devices: List[Dict], min_severity: int = 7) -> Dict[str, Any]:
        """
        Scan entire fleet for CVE vulnerabilities based on OS versions
        
        Args:
            devices: List of device dictionaries
            min_severity: Minimum CVE severity to report (0-10), default 7 (High+Critical)
            
        Returns:
            Dictionary with vulnerability analysis
        """
        logger.info(f"Starting fleet CVE scan with min_severity={min_severity}")
        
        # Group devices by OS version and security patch
        android_by_patch = defaultdict(list)
        ios_by_version = defaultdict(list)
        
        for device in devices:
            platform = device.get('platform', '').lower()
            
            if platform == 'android':
                patch_level = device.get('security_patch_level')
                if patch_level and patch_level != 'N/A':
                    android_by_patch[patch_level].append(device)
            elif platform == 'ios':
                os_version = device.get('os_version')
                if os_version and os_version != 'Unknown':
                    ios_by_version[os_version].append(device)
        
        logger.info(f"Grouped devices: {len(android_by_patch)} Android patches, {len(ios_by_version)} iOS versions")
        
        # Scan vulnerabilities for each unique OS version/patch
        vulnerability_summary = {
            'total_devices_scanned': len(devices),
            'android_patches_scanned': len(android_by_patch),
            'ios_versions_scanned': len(ios_by_version),
            'vulnerabilities_by_severity': defaultdict(int),
            'top_cves': [],
            'affected_devices_count': 0,
            'vulnerabilities_found': []
        }
        
        cve_device_map = defaultdict(set)  # Track unique devices per CVE
        
        # Scan Android devices
        for patch_level, patch_devices in android_by_patch.items():
            logger.info(f"Scanning Android patch level {patch_level} ({len(patch_devices)} devices)")
            vulns = self.get_vulnerabilities_for_android_patch(patch_level, min_severity)
            logger.info(f"Found {len(vulns)} vulnerabilities for Android patch {patch_level}")
            
            for vuln_wrapper in vulns:
                # Extract nested vulnerability object if present
                vuln = vuln_wrapper.get('vulnerability', vuln_wrapper) if isinstance(vuln_wrapper, dict) else vuln_wrapper
                
                # Try different field names for CVE identifier
                cve_name = vuln.get('name') or vuln.get('cve') or vuln.get('cve_id') or vuln.get('id')
                if not cve_name:
                    logger.warning(f"No CVE name found in vulnerability: {vuln.keys()}")
                    continue
                
                severity = float(vuln.get('severity', 0) or vuln.get('cvss_score', 0) or 0)
                
                # Track severity distribution
                if severity >= 9:
                    vulnerability_summary['vulnerabilities_by_severity']['Critical'] += 1
                elif severity >= 7:
                    vulnerability_summary['vulnerabilities_by_severity']['High'] += 1
                elif severity >= 4:
                    vulnerability_summary['vulnerabilities_by_severity']['Medium'] += 1
                else:
                    vulnerability_summary['vulnerabilities_by_severity']['Low'] += 1
                
                # Track affected devices
                for device in patch_devices:
                    cve_device_map[cve_name].add(device.get('device_id'))
                
                # Add to vulnerabilities list
                vulnerability_summary['vulnerabilities_found'].append({
                    'cve': cve_name,
                    'severity': severity,
                    'severity_label': self._severity_label(severity),
                    'platform': 'Android',
                    'patch_level': patch_level,
                    'affected_device_count': len(patch_devices),
                    'description': vuln.get('description', '') or vuln.get('summary', '') or 'No description available'
                })
        
        # Scan iOS devices
        for ios_version, version_devices in ios_by_version.items():
            logger.info(f"Scanning iOS version {ios_version} ({len(version_devices)} devices)")
            vulns = self.get_vulnerabilities_for_ios_version(ios_version, min_severity)
            logger.info(f"Found {len(vulns)} vulnerabilities for iOS {ios_version}")
            
            for vuln_wrapper in vulns:
                # Extract nested vulnerability object if present
                vuln = vuln_wrapper.get('vulnerability', vuln_wrapper) if isinstance(vuln_wrapper, dict) else vuln_wrapper
                
                # Try different field names for CVE identifier
                cve_name = vuln.get('name') or vuln.get('cve') or vuln.get('cve_id') or vuln.get('id')
                if not cve_name:
                    logger.warning(f"No CVE name found in vulnerability: {vuln.keys()}")
                    continue
                
                severity = float(vuln.get('severity', 0) or vuln.get('cvss_score', 0) or 0)
                
                # Track severity distribution
                if severity >= 9:
                    vulnerability_summary['vulnerabilities_by_severity']['Critical'] += 1
                elif severity >= 7:
                    vulnerability_summary['vulnerabilities_by_severity']['High'] += 1
                elif severity >= 4:
                    vulnerability_summary['vulnerabilities_by_severity']['Medium'] += 1
                else:
                    vulnerability_summary['vulnerabilities_by_severity']['Low'] += 1
                
                # Track affected devices
                for device in version_devices:
                    cve_device_map[cve_name].add(device.get('device_id'))
                
                # Add to vulnerabilities list
                vulnerability_summary['vulnerabilities_found'].append({
                    'cve': cve_name,
                    'severity': severity,
                    'severity_label': self._severity_label(severity),
                    'platform': 'iOS',
                    'os_version': ios_version,
                    'affected_device_count': len(version_devices),
                    'description': vuln.get('description', '') or vuln.get('summary', '') or 'No description available'
                })
        
        # Calculate total unique affected devices (deduplicated across all CVEs)
        all_affected_devices = set()
        for devices_set in cve_device_map.values():
            all_affected_devices.update(devices_set)
        vulnerability_summary['affected_devices_count'] = len(all_affected_devices)
        
        logger.info(f"Total unique devices affected: {len(all_affected_devices)}")
        
        # Get top CVEs by affected device count
        cve_counts = [(cve, len(device_ids)) for cve, device_ids in cve_device_map.items()]
        cve_counts.sort(key=lambda x: x[1], reverse=True)
        vulnerability_summary['top_cves'] = [
            {'cve': cve, 'affected_devices': count}
            for cve, count in cve_counts[:10]
        ]
        
        logger.info(f"Fleet scan complete: {len(vulnerability_summary['vulnerabilities_found'])} vulnerabilities found")
        
        return vulnerability_summary
    
    def _severity_label(self, severity: float) -> str:
        """Convert numeric severity to label"""
        if severity >= 9:
            return 'Critical'
        elif severity >= 7:
            return 'High'
        elif severity >= 4:
            return 'Medium'
        else:
            return 'Low'
    
    def get_vulnerability_report(self, devices: List[Dict], min_severity: int = 7) -> Dict[str, Any]:
        """
        Generate comprehensive vulnerability report for the fleet
        
        Args:
            devices: List of device dictionaries
            min_severity: Minimum severity threshold
            
        Returns:
            Formatted report with summary and details
        """
        scan_results = self.scan_fleet_vulnerabilities(devices, min_severity)
        
        # Calculate additional metrics
        total_devices = scan_results['total_devices_scanned']
        affected_count = scan_results['affected_devices_count']
        affected_percentage = (affected_count / total_devices * 100) if total_devices > 0 else 0
        
        report = {
            'summary': {
                'total_devices': total_devices,
                'devices_with_vulnerabilities': affected_count,
                'vulnerability_percentage': round(affected_percentage, 2),
                'total_cves_found': len(set([v['cve'] for v in scan_results['vulnerabilities_found']])),
                'severity_breakdown': dict(scan_results['vulnerabilities_by_severity'])
            },
            'top_cves': scan_results['top_cves'],
            'all_vulnerabilities': scan_results['vulnerabilities_found'],
            'scan_metadata': {
                'android_patches_scanned': scan_results['android_patches_scanned'],
                'ios_versions_scanned': scan_results['ios_versions_scanned'],
                'minimum_severity': min_severity
            }
        }
        
        return report
