"""
Tests for the CVEService class.
"""

from unittest.mock import MagicMock

from services.cve_service import CVEService


def make_client(android_vulns=None, ios_vulns=None):
    client = MagicMock()
    client.is_authenticated.return_value = True
    client.get_android_vulnerabilities.return_value = {'vulnerabilities': android_vulns or []}
    client.get_ios_vulnerabilities.return_value = {'vulnerabilities': ios_vulns or []}
    return client


class TestScanFleetVulnerabilities:
    """Test suite for scan_fleet_vulnerabilities"""

    def test_buckets_by_severity_label(self):
        android_vulns = [
            {'name': 'CVE-2024-0001', 'severity': 9.5},
            {'name': 'CVE-2024-0002', 'severity': 7.0},
            {'name': 'CVE-2024-0003', 'severity': 5.0},
            {'name': 'CVE-2024-0004', 'severity': 2.0},
        ]
        client = make_client(android_vulns=android_vulns)
        service = CVEService(client)
        devices = [
            {'device_id': 'd1', 'platform': 'android', 'security_patch_level': '2024-01-01'},
        ]

        report = service.scan_fleet_vulnerabilities(devices, min_severity=0)

        assert report['summary']['severity_breakdown'] == {
            'Critical': 1, 'High': 1, 'Medium': 1, 'Low': 1
        }

    def test_dedupes_cve_across_multiple_devices_on_same_patch(self):
        android_vulns = [{'name': 'CVE-2024-0001', 'severity': 8.0}]
        client = make_client(android_vulns=android_vulns)
        service = CVEService(client)
        devices = [
            {'device_id': 'd1', 'platform': 'android', 'security_patch_level': '2024-01-01'},
            {'device_id': 'd2', 'platform': 'android', 'security_patch_level': '2024-01-01'},
        ]

        report = service.scan_fleet_vulnerabilities(devices, min_severity=0)

        assert report['summary']['total_cves_found'] == 1
        assert report['summary']['devices_with_vulnerabilities'] == 2
        assert report['top_cves'][0]['affected_devices'] == 2

    def test_unwraps_nested_vulnerability_object(self):
        android_vulns = [{'vulnerability': {'name': 'CVE-2024-0001', 'severity': 9.0}}]
        client = make_client(android_vulns=android_vulns)
        service = CVEService(client)
        devices = [{'device_id': 'd1', 'platform': 'android', 'security_patch_level': '2024-01-01'}]

        report = service.scan_fleet_vulnerabilities(devices, min_severity=0)

        assert report['all_vulnerabilities'][0]['cve'] == 'CVE-2024-0001'
        assert report['all_vulnerabilities'][0]['severity_label'] == 'Critical'

    def test_top_cves_sorted_by_severity_then_affected_device_count(self):
        android_vulns = [
            {'name': 'CVE-low-severity-wide', 'severity': 4.0},
            {'name': 'CVE-high-severity', 'severity': 9.0},
        ]
        client = make_client(android_vulns=android_vulns)
        service = CVEService(client)
        devices = [
            {'device_id': 'd1', 'platform': 'android', 'security_patch_level': '2024-01-01'},
            {'device_id': 'd2', 'platform': 'android', 'security_patch_level': '2024-01-01'},
        ]

        report = service.scan_fleet_vulnerabilities(devices, min_severity=0)

        assert report['top_cves'][0]['cve'] == 'CVE-high-severity'

    def test_combines_android_and_ios_devices(self):
        client = make_client(
            android_vulns=[{'name': 'CVE-android', 'severity': 8.0}],
            ios_vulns=[{'name': 'CVE-ios', 'severity': 6.0}],
        )
        service = CVEService(client)
        devices = [
            {'device_id': 'd1', 'platform': 'android', 'security_patch_level': '2024-01-01'},
            {'device_id': 'd2', 'platform': 'ios', 'os_version': '17.2.1'},
        ]

        report = service.scan_fleet_vulnerabilities(devices, min_severity=0)

        cve_ids = {v['cve'] for v in report['all_vulnerabilities']}
        assert cve_ids == {'CVE-android', 'CVE-ios'}
        assert report['summary']['total_devices'] == 2

    def test_empty_device_list(self):
        client = make_client()
        service = CVEService(client)

        report = service.scan_fleet_vulnerabilities([], min_severity=0)

        assert report['summary']['total_devices'] == 0
        assert report['summary']['vulnerability_percentage'] == 0
        assert report['all_vulnerabilities'] == []
        assert report['top_cves'] == []
