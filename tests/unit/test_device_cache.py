"""
Tests for DeviceCache tenant sync status tracking.
"""

from device_cache import DeviceCache


class TestTenantSyncStatus:
    """Test suite for record_tenant_sync_success/failure and get_tenant_sync_status"""

    def test_record_success_then_read_back(self):
        cache = DeviceCache(enable_persistence=False)

        cache.record_tenant_sync_success('tenant_1', 'Company A', 42)

        statuses = cache.get_tenant_sync_status()
        assert len(statuses) == 1
        status = statuses[0]
        assert status['tenant_id'] == 'tenant_1'
        assert status['tenant_name'] == 'Company A'
        assert status['status'] == 'ok'
        assert status['last_success'] is not None
        assert status['last_error'] is None
        assert status['error_message'] is None
        assert status['device_count'] == 42

    def test_failure_preserves_prior_success_and_device_count(self):
        cache = DeviceCache(enable_persistence=False)

        cache.record_tenant_sync_success('tenant_1', 'Company A', 42)
        prior_success_time = cache.get_tenant_sync_status()[0]['last_success']

        cache.record_tenant_sync_failure('tenant_1', 'Company A', 'expired key')

        status = cache.get_tenant_sync_status()[0]
        assert status['status'] == 'error'
        assert status['last_success'] == prior_success_time
        assert status['device_count'] == 42
        assert status['last_error'] is not None
        assert status['error_message'] == 'expired key'

    def test_failure_with_no_prior_entry_defaults_last_success_and_device_count(self):
        cache = DeviceCache(enable_persistence=False)

        cache.record_tenant_sync_failure('tenant_1', 'Company A', 'connection refused')

        status = cache.get_tenant_sync_status()[0]
        assert status['status'] == 'error'
        assert status['last_success'] is None
        assert status['device_count'] == 0
        assert status['error_message'] == 'connection refused'

    def test_fresh_success_after_failure_clears_error_fields(self):
        cache = DeviceCache(enable_persistence=False)

        cache.record_tenant_sync_failure('tenant_1', 'Company A', 'expired key')
        cache.record_tenant_sync_success('tenant_1', 'Company A', 10)

        status = cache.get_tenant_sync_status()[0]
        assert status['status'] == 'ok'
        assert status['last_error'] is None
        assert status['error_message'] is None
        assert status['device_count'] == 10


class TestPurgeTenantDevices:
    """Test suite for purge_tenant_devices"""

    def test_removes_only_matching_tenant_devices_and_returns_count(self):
        cache = DeviceCache(enable_persistence=False)
        cache.update_devices([
            {'device_id': 'd1', 'tenant_id': 'tenant_1'},
            {'device_id': 'd2', 'tenant_id': 'tenant_1'},
            {'device_id': 'd3', 'tenant_id': 'tenant_2'},
        ])

        removed_count = cache.purge_tenant_devices('tenant_1')

        assert removed_count == 2
        remaining_ids = {d['device_id'] for d in cache.get_all_devices()}
        assert remaining_ids == {'d3'}
        assert cache.cache_metadata['total_devices'] == 1

    def test_clears_tenant_sync_status_entry(self):
        cache = DeviceCache(enable_persistence=False)
        cache.record_tenant_sync_success('tenant_1', 'Company A', 5)

        cache.purge_tenant_devices('tenant_1')

        assert cache.tenant_sync_status.get('tenant_1') is None
