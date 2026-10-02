"""
CVE Vulnerability Service

Handles CVE vulnerability scanning and analysis for the device fleet.
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

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
        Scan entire fleet for CVE vulnerabilities based on OS versions and security patch levels

        Args:
            devices: List of device dictionaries
            min_severity: Minimum CVE severity to report (0-10), default 7 (High+Critical)

        Returns:
            Vulnerability report dictionary with summary, top_cves, all_vulnerabilities, scan_metadata
        """
        logger.info(f"Starting fleet CVE scan with min_severity={min_severity}")

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

        all_vulnerabilities = []
        affected_devices = set()
        cve_device_map = {}  # cve_id -> set of device_ids

        for patch in android_patches:
            vulns = self.get_vulnerabilities_for_android_patch(patch, min_severity)
            patch_devices = devices_by_android_patch.get(patch, [])
            for vuln_wrapper in vulns:
                # Unwrap nested vulnerability object
                vuln = vuln_wrapper.get('vulnerability', vuln_wrapper) if isinstance(vuln_wrapper, dict) else vuln_wrapper
                cve_id = vuln.get('name') or vuln.get('cve') or vuln.get('cve_id') or 'Unknown'
                severity = float(vuln.get('severity', 0) or 0)

                all_vulnerabilities.append({
                    'cve': cve_id,
                    'severity': severity,
                    'severity_label': self._severity_label(severity),
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
            vulns = self.get_vulnerabilities_for_ios_version(version, min_severity)
            ver_devices = devices_by_ios_version.get(version, [])
            for vuln_wrapper in vulns:
                # Unwrap nested vulnerability object
                vuln = vuln_wrapper.get('vulnerability', vuln_wrapper) if isinstance(vuln_wrapper, dict) else vuln_wrapper
                cve_id = vuln.get('name') or vuln.get('cve') or vuln.get('cve_id') or 'Unknown'
                severity = float(vuln.get('severity', 0) or 0)

                all_vulnerabilities.append({
                    'cve': cve_id,
                    'severity': severity,
                    'severity_label': self._severity_label(severity),
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

        logger.info(f"Fleet scan complete: {len(all_vulnerabilities)} vulnerabilities found across {unique_cve_count} unique CVEs")

        return {
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
        }

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
