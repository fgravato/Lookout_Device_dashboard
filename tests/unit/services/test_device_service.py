"""
Tests for DeviceService.get_cve_client() and fetch_and_cache_devices() concurrency.
"""

import threading
from unittest.mock import MagicMock, patch

from lookout_client import LookoutAPIError
from services.device_service import DeviceService
from services.tenant_service import Tenant


def make_tenant(tenant_id='tenant_1', enabled=True):
    return Tenant(
        tenant_id=tenant_id,
        tenant_name=f'Company {tenant_id}',
        mdm_provider='InTune',
        mdm_identifier=f'intune-{tenant_id}',
        lookout_application_key=f'key-{tenant_id}',
        enabled=enabled,
    )


class TestGetCveClient:
    """Test suite for DeviceService.get_cve_client()"""

    def test_multi_tenant_mode_uses_first_enabled_tenants_client(self):
        config = MagicMock()
        config.ENABLE_MULTI_TENANT = True
        tenant_service = MagicMock()
        tenant_service.get_all_tenants.return_value = [make_tenant('tenant_1')]

        with patch('services.device_service.LookoutMRAClient') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.is_authenticated.return_value = True
            mock_client_cls.return_value = mock_client

            service = DeviceService(config, device_cache=MagicMock(), tenant_service=tenant_service)
            client = service.get_cve_client()

        assert client is mock_client
        mock_client_cls.assert_called_once_with(application_key='key-tenant_1', config=config)
        tenant_service.get_all_tenants.assert_called_once_with(enabled_only=True)

    def test_multi_tenant_mode_returns_none_when_no_enabled_tenants(self):
        config = MagicMock()
        config.ENABLE_MULTI_TENANT = True
        tenant_service = MagicMock()
        tenant_service.get_all_tenants.return_value = []

        service = DeviceService(config, device_cache=MagicMock(), tenant_service=tenant_service)
        client = service.get_cve_client()

        assert client is None

    def test_multi_tenant_mode_returns_none_when_tenant_auth_fails(self):
        config = MagicMock()
        config.ENABLE_MULTI_TENANT = True
        tenant_service = MagicMock()
        tenant_service.get_all_tenants.return_value = [make_tenant('tenant_1')]

        with patch('services.device_service.LookoutMRAClient') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.authenticate.side_effect = LookoutAPIError('bad credentials')
            mock_client_cls.return_value = mock_client

            service = DeviceService(config, device_cache=MagicMock(), tenant_service=tenant_service)
            client = service.get_cve_client()

        assert client is None

    def test_single_tenant_mode_uses_global_client(self):
        config = MagicMock()
        config.ENABLE_MULTI_TENANT = False

        service = DeviceService(config, device_cache=MagicMock(), tenant_service=None)
        sentinel_client = MagicMock()
        service.get_lookout_client = MagicMock(return_value=sentinel_client)

        client = service.get_cve_client()

        assert client is sentinel_client
        service.get_lookout_client.assert_called_once()


class TestFetchAndCacheDevicesConcurrency:
    """A stale cache + two near-simultaneous requests (e.g. Full Refresh and a
    CVE scan started right after) must not trigger two concurrent API fetches -
    that's what trips the Lookout API's rate limit and makes the second caller
    fail. The second caller should wait for and reuse the first's result."""

    def test_concurrent_calls_coalesce_into_a_single_underlying_fetch(self):
        config = MagicMock()
        config.USE_SAMPLE_DATA = False
        config.ENABLE_MULTI_TENANT = False

        service = DeviceService(config, device_cache=MagicMock(), tenant_service=None)

        fetch_started = threading.Event()
        release_fetch = threading.Event()
        call_count = []

        def slow_fetch():
            call_count.append(1)
            fetch_started.set()
            release_fetch.wait(timeout=5)
            return [{'device_id': 'd1'}]

        service._fetch_from_api = MagicMock(side_effect=slow_fetch)

        results = []

        def caller():
            results.append(service.fetch_and_cache_devices())

        first = threading.Thread(target=caller)
        first.start()
        assert fetch_started.wait(timeout=5), "first fetch never started"

        second = threading.Thread(target=caller)
        second.start()

        # Give the second thread time to reach and block on the fetch lock
        # before we let the first fetch complete.
        threading.Event().wait(0.2)
        release_fetch.set()

        first.join(timeout=5)
        second.join(timeout=5)

        assert len(call_count) == 1, "underlying fetch ran more than once concurrently"
        assert results[0] == results[1] == [{'device_id': 'd1'}]

    def test_waiting_caller_sees_the_leaders_failure_not_stale_data(self):
        config = MagicMock()
        config.USE_SAMPLE_DATA = False
        config.ENABLE_MULTI_TENANT = False

        service = DeviceService(config, device_cache=MagicMock(), tenant_service=None)

        fetch_started = threading.Event()
        release_fetch = threading.Event()

        def failing_fetch():
            fetch_started.set()
            release_fetch.wait(timeout=5)
            raise LookoutAPIError("rate limited")

        service._fetch_from_api = MagicMock(side_effect=failing_fetch)

        errors = []

        def caller():
            try:
                service.fetch_and_cache_devices()
            except LookoutAPIError as e:
                errors.append(e)

        first = threading.Thread(target=caller)
        first.start()
        assert fetch_started.wait(timeout=5), "first fetch never started"

        second = threading.Thread(target=caller)
        second.start()

        threading.Event().wait(0.2)
        release_fetch.set()

        first.join(timeout=5)
        second.join(timeout=5)

        assert len(errors) == 2, "both callers should see the failure, not silently succeed"


class TestFetchFromAllTenants:
    """A tenant whose connector breaks (expired key, MDM sync failure) must not
    silently drop out of the fleet - the failure should be recorded on the
    device cache while other tenants are still processed."""

    def test_one_failing_tenant_does_not_block_others_and_records_status(self):
        config = MagicMock()
        config.USE_SAMPLE_DATA = False
        config.ENABLE_MULTI_TENANT = True

        tenant_service = MagicMock()
        good_tenant = make_tenant('tenant_1')
        bad_tenant = make_tenant('tenant_2')
        tenant_service.get_all_tenants.return_value = [bad_tenant, good_tenant]

        device_cache = MagicMock()
        service = DeviceService(config, device_cache=device_cache, tenant_service=tenant_service)

        error = Exception('expired application key')

        def fake_get_tenant_client(tenant):
            return MagicMock()

        def fake_fetch_all_devices_efficiently(client):
            # Determine which tenant this call is for based on call order
            call_index = fake_fetch_all_devices_efficiently.call_count
            fake_fetch_all_devices_efficiently.call_count += 1
            if call_index == 0:
                raise error
            return [{'guid': 'device-1'}]

        fake_fetch_all_devices_efficiently.call_count = 0

        service._get_tenant_client = MagicMock(side_effect=fake_get_tenant_client)
        service._fetch_all_devices_efficiently = MagicMock(side_effect=fake_fetch_all_devices_efficiently)

        devices = service._fetch_from_all_tenants()

        # Failure isolated: good tenant's device still made it into the result
        assert len(devices) == 1
        assert devices[0]['tenant_id'] == 'tenant_1'

        device_cache.record_tenant_sync_failure.assert_called_once_with(
            'tenant_2', bad_tenant.tenant_name, str(error)
        )
        device_cache.record_tenant_sync_success.assert_called_once_with(
            'tenant_1', good_tenant.tenant_name, 1
        )


class TestDropTenantClient:
    """Test suite for DeviceService.drop_tenant_client()"""

    def test_removes_cached_client_for_tenant(self):
        config = MagicMock()
        service = DeviceService(config, device_cache=MagicMock(), tenant_service=None)
        service.tenant_clients['tenant_1'] = MagicMock()

        service.drop_tenant_client('tenant_1')

        assert 'tenant_1' not in service.tenant_clients

    def test_no_error_when_tenant_id_never_cached(self):
        config = MagicMock()
        service = DeviceService(config, device_cache=MagicMock(), tenant_service=None)

        service.drop_tenant_client('unknown_tenant')

        assert 'unknown_tenant' not in service.tenant_clients
