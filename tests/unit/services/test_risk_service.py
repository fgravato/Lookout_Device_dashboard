"""
Tests for the RiskService class.
"""

import pytest

from services.risk_service import RiskService


class TestGroupDevicesByRisk:
    """Test suite for group_devices_by_risk method"""

    def test_groups_devices_into_expected_buckets(self):
        """Test devices are bucketed by risk level and connection status"""
        devices = [
            {'device_id': 'd1', 'risk_level': 'Critical', 'days_since_checkin': 1},
            {'device_id': 'd2', 'risk_level': 'High', 'days_since_checkin': 2},
            {'device_id': 'd3', 'risk_level': 'Medium', 'days_since_checkin': 3},
            {'device_id': 'd4', 'risk_level': 'Low', 'days_since_checkin': 4},
            {'device_id': 'd5', 'risk_level': 'Secure', 'days_since_checkin': 5},
            {'device_id': 'd6', 'risk_level': 'Secure', 'days_since_checkin': -1},
            {'device_id': 'd7', 'risk_level': 'Low', 'days_since_checkin': 45},
        ]

        result = RiskService.group_devices_by_risk(devices)

        groups = result['groups']
        assert [d['device_id'] for d in groups['high_risk']['devices']] == ['d1', 'd2']
        assert [d['device_id'] for d in groups['medium_risk']['devices']] == ['d3']
        assert [d['device_id'] for d in groups['low_risk']['devices']] == ['d4', 'd7']
        assert [d['device_id'] for d in groups['secure']['devices']] == ['d5', 'd6']
        assert [d['device_id'] for d in groups['never_connected']['devices']] == ['d6']
        assert [d['device_id'] for d in groups['stale']['devices']] == ['d7']

    def test_counts_match_group_sizes(self):
        """Test counts dict reflects the number of devices in each group"""
        devices = [
            {'device_id': 'd1', 'risk_level': 'Critical', 'days_since_checkin': 1},
            {'device_id': 'd2', 'risk_level': 'Critical', 'days_since_checkin': 1},
        ]

        result = RiskService.group_devices_by_risk(devices)

        assert result['counts']['high_risk'] == 2
        assert result['total_devices'] == 2

    def test_empty_groups_are_removed(self):
        """Test groups with no devices are excluded from the result"""
        devices = [
            {'device_id': 'd1', 'risk_level': 'Secure', 'days_since_checkin': 1},
        ]

        result = RiskService.group_devices_by_risk(devices)

        assert set(result['groups'].keys()) == {'secure'}
        assert set(result['counts'].keys()) == {'secure'}

    def test_empty_device_list(self):
        """Test grouping an empty device list returns no groups"""
        result = RiskService.group_devices_by_risk([])

        assert result['groups'] == {}
        assert result['counts'] == {}
        assert result['total_devices'] == 0
