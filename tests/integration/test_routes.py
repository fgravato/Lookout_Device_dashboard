"""
Integration tests for Flask routes.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestHealthEndpoint:
    """Test suite for health check endpoint"""
    
    def test_health_check_returns_200(self, client, app):
        """Test health endpoint returns healthy status"""
        # Mock the device cache
        mock_cache = MagicMock()
        mock_cache.is_valid.return_value = True
        mock_cache.get_stats.return_value = {
            'cached_devices': 100,
            'cache_age_minutes': 5,
            'last_sync_time': '2024-01-15T10:00:00Z'
        }
        app.extensions['device_cache'] = mock_cache
        
        # Mock device service
        mock_service = MagicMock()
        mock_service.get_lookout_client.return_value = MagicMock()
        app.extensions['device_service'] = mock_service
        
        response = client.get('/health')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'healthy'
        assert 'cache' in data
        assert data['cache']['device_count'] == 100


class TestDeviceRoutes:
    """Test suite for device-related routes"""
    
    def test_index_page_returns_200(self, client, app):
        """Test main dashboard page loads"""
        # Mock template rendering
        with patch('routes.devices.render_template') as mock_render:
            mock_render.return_value = '<html>Dashboard</html>'
            response = client.get('/')
            assert response.status_code == 200
    
    def test_get_devices_returns_device_list(self, client, app, sample_devices):
        """Test /api/devices returns list of devices"""
        # Mock device service
        mock_service = MagicMock()
        mock_service.get_cached_devices.return_value = sample_devices
        mock_service.get_or_refresh_devices.return_value = sample_devices
        mock_service.get_cache_stats.return_value = {
            'last_sync_time': '2024-01-15T10:00:00Z',
            'cache_age_minutes': 5,
            'api_response_time': 1.5
        }
        app.extensions['device_service'] = mock_service
        
        mock_cache = MagicMock()
        mock_cache.is_valid.return_value = True
        app.extensions['device_cache'] = mock_cache
        
        response = client.get('/api/devices')
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'devices' in data
        assert 'total_count' in data
        assert data['total_count'] == 3
        assert 'cache_info' in data
    
    def test_get_device_details_returns_device(self, client, app, sample_device):
        """Test /api/device/<id> returns specific device"""
        # Mock device service
        mock_service = MagicMock()
        mock_service.get_cached_devices.return_value = [sample_device]
        mock_service.get_or_refresh_devices.return_value = [sample_device]
        app.extensions['device_service'] = mock_service
        
        response = client.get('/api/device/test-device-001')
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'device' in data
        assert data['device']['device_id'] == 'test-device-001'
        assert 'risk_analysis' in data
    
    def test_get_device_details_returns_404_for_unknown(self, client, app):
        """Test /api/device/<id> returns 404 for unknown device"""
        # Mock device service with empty list
        mock_service = MagicMock()
        mock_service.get_cached_devices.return_value = []
        app.extensions['device_service'] = mock_service
        
        response = client.get('/api/device/unknown-device')
        
        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data


class TestCacheRoutes:
    """Test suite for cache management routes"""
    
    def test_get_cache_stats_returns_stats(self, client, app):
        """Test /api/cache/stats returns cache statistics"""
        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = {
            'cached_devices': 100,
            'cache_age_minutes': 5,
            'last_sync_time': '2024-01-15T10:00:00Z'
        }
        app.extensions['device_cache'] = mock_cache
        
        response = client.get('/api/cache/stats')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['cached_devices'] == 100
    
    def test_clear_cache_returns_success(self, client, app):
        """Test /api/cache/clear clears the cache"""
        mock_cache = MagicMock()
        app.extensions['device_cache'] = mock_cache

        response = client.post('/api/cache/clear')
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'message' in data
        mock_cache.clear.assert_called_once()


class TestExportRoutes:
    """Test suite for export routes"""
    
    def test_export_excel_returns_file(self, client, app, sample_devices):
        """Test /api/export/excel returns Excel file"""
        # Mock services
        mock_service = MagicMock()
        mock_service.get_cached_devices.return_value = sample_devices
        app.extensions['device_service'] = mock_service
        
        mock_export = MagicMock()
        mock_export.export_devices_to_excel.return_value = '/tmp/test_export.xlsx'
        app.extensions['export_service'] = mock_export
        
        # Create a temporary file for testing
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
            tmp.write(b'fake excel content')
            tmp_path = tmp.name
        
        mock_export.export_devices_to_excel.return_value = tmp_path
        
        with patch('routes.export.send_file') as mock_send:
            mock_send.return_value = 'file sent'
            response = client.get('/api/export/excel')
            
            # Should call send_file
            mock_send.assert_called_once()
        
        # Cleanup (route's after_this_request handler already removes the file)
        import os
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass


class TestTenantRoutes:
    """Test suite for tenant routes"""

    def test_get_tenants_merges_sync_status(self, client, app):
        """Test /api/tenants merges per-tenant sync status into each tenant dict"""
        mock_config_class = MagicMock()
        mock_config_class.ENABLE_MULTI_TENANT = True
        mock_config_class.AUTH_ENABLED = False
        app.extensions['config_class'] = mock_config_class

        mock_tenant_service = MagicMock()
        mock_tenant_service.get_tenants_summary.return_value = {
            'total_tenants': 2,
            'enabled_tenants': 2,
            'disabled_tenants': 0,
            'mdm_providers': ['InTune'],
            'tenants': [
                {'tenant_id': 'tenant_1', 'tenant_name': 'Company A', 'mdm_provider': 'InTune',
                 'mdm_identifier': 'intune-1', 'description': '', 'enabled': True},
                {'tenant_id': 'tenant_2', 'tenant_name': 'Company B', 'mdm_provider': 'InTune',
                 'mdm_identifier': 'intune-2', 'description': '', 'enabled': True},
            ]
        }
        app.extensions['tenant_service'] = mock_tenant_service

        mock_cache = MagicMock()
        mock_cache.get_tenant_sync_status.return_value = [
            {'tenant_id': 'tenant_1', 'tenant_name': 'Company A', 'status': 'ok',
             'last_success': '2024-01-15T10:00:00', 'last_error': None,
             'error_message': None, 'device_count': 10},
        ]
        app.extensions['device_cache'] = mock_cache

        response = client.get('/api/tenants')

        assert response.status_code == 200
        data = response.get_json()
        tenants_by_id = {t['tenant_id']: t for t in data['tenants']}

        assert tenants_by_id['tenant_1']['status'] == 'ok'
        assert tenants_by_id['tenant_1']['device_count'] == 10

        # Tenant with no recorded status yet defaults to 'unknown'
        assert tenants_by_id['tenant_2']['status'] == 'unknown'
        assert tenants_by_id['tenant_2']['last_success'] is None
        assert tenants_by_id['tenant_2']['device_count'] == 0

        # Existing top-level fields untouched
        assert data['total_tenants'] == 2
        assert data['enabled_tenants'] == 2

    def test_disabled_tenant_shows_disabled_not_stale_ok_status(self, client, app):
        """A disabled tenant's last recorded sync status (from before it was
        disabled) must not be shown as if it's still actively 'ok' - that
        misleads an admin into thinking an offboarded tenant is still monitored."""
        mock_config_class = MagicMock()
        mock_config_class.ENABLE_MULTI_TENANT = True
        mock_config_class.AUTH_ENABLED = False
        app.extensions['config_class'] = mock_config_class

        mock_tenant_service = MagicMock()
        mock_tenant_service.get_tenants_summary.return_value = {
            'total_tenants': 1,
            'enabled_tenants': 0,
            'disabled_tenants': 1,
            'mdm_providers': [],
            'tenants': [
                {'tenant_id': 'tenant_1', 'tenant_name': 'Offboarded Co', 'mdm_provider': 'InTune',
                 'mdm_identifier': 'intune-1', 'description': '', 'enabled': False},
            ]
        }
        app.extensions['tenant_service'] = mock_tenant_service

        mock_cache = MagicMock()
        mock_cache.get_tenant_sync_status.return_value = [
            {'tenant_id': 'tenant_1', 'tenant_name': 'Offboarded Co', 'status': 'ok',
             'last_success': '2024-01-15T10:00:00', 'last_error': None,
             'error_message': None, 'device_count': 42},
        ]
        app.extensions['device_cache'] = mock_cache

        response = client.get('/api/tenants')

        assert response.status_code == 200
        tenant = response.get_json()['tenants'][0]
        assert tenant['status'] == 'disabled'
        assert tenant['last_success'] is None
        assert tenant['device_count'] == 0

    def test_create_tenant_success(self, client, app):
        """Test POST /api/tenants returns 201 with no key in response body"""
        mock_config_class = MagicMock()
        mock_config_class.ENABLE_MULTI_TENANT = True
        mock_config_class.AUTH_ENABLED = False
        app.extensions['config_class'] = mock_config_class

        mock_tenant_service = MagicMock()
        mock_tenant = MagicMock()
        mock_tenant.to_dict.return_value = {
            'tenant_id': 'tenant_1', 'tenant_name': 'Company A', 'mdm_provider': 'InTune',
            'mdm_identifier': 'intune-1', 'description': '', 'enabled': True
        }
        mock_tenant_service.add_tenant.return_value = mock_tenant
        app.extensions['tenant_service'] = mock_tenant_service

        response = client.post('/api/tenants', json={
            'tenant_id': 'tenant_1',
            'tenant_name': 'Company A',
            'mdm_provider': 'InTune',
            'mdm_identifier': 'intune-1',
            'lookout_application_key': 'secret-key'
        })

        assert response.status_code == 201
        data = response.get_json()
        assert 'lookout_application_key' not in data
        assert data['tenant_id'] == 'tenant_1'

    def test_create_tenant_duplicate_id_returns_409(self, client, app):
        """Test POST /api/tenants returns 409 when tenant_id already exists"""
        mock_config_class = MagicMock()
        mock_config_class.ENABLE_MULTI_TENANT = True
        mock_config_class.AUTH_ENABLED = False
        app.extensions['config_class'] = mock_config_class

        mock_tenant_service = MagicMock()
        mock_tenant_service.add_tenant.side_effect = ValueError("Tenant 'tenant_1' already exists")
        app.extensions['tenant_service'] = mock_tenant_service

        response = client.post('/api/tenants', json={
            'tenant_id': 'tenant_1',
            'tenant_name': 'Company A',
            'mdm_provider': 'InTune',
            'mdm_identifier': 'intune-1',
            'lookout_application_key': 'secret-key'
        })

        assert response.status_code == 409
        assert response.get_json()['error']['code'] == 'TENANT_CONFLICT'

    def test_create_tenant_duplicate_mdm_identifier_returns_409(self, client, app):
        """Test POST /api/tenants returns 409 when mdm_identifier is already used
        by another tenant - a silent collision here breaks MDM-identifier-scoped
        device routing (get_tenant_by_mdm_identifier, /api/mdm/<id>/devices)."""
        mock_config_class = MagicMock()
        mock_config_class.ENABLE_MULTI_TENANT = True
        mock_config_class.AUTH_ENABLED = False
        app.extensions['config_class'] = mock_config_class

        mock_tenant_service = MagicMock()
        mock_tenant_service.add_tenant.side_effect = ValueError(
            "mdm_identifier 'intune-1' is already used by another tenant"
        )
        app.extensions['tenant_service'] = mock_tenant_service

        response = client.post('/api/tenants', json={
            'tenant_id': 'tenant_2',
            'tenant_name': 'Company B',
            'mdm_provider': 'InTune',
            'mdm_identifier': 'intune-1',
            'lookout_application_key': 'secret-key'
        })

        assert response.status_code == 409
        assert response.get_json()['error']['code'] == 'TENANT_CONFLICT'

    def test_update_tenant_blank_required_field_returns_400(self, client, app):
        """Test PUT /api/tenants/<id> returns 400 (not 500) when a required
        field would be blanked out."""
        mock_config_class = MagicMock()
        mock_config_class.ENABLE_MULTI_TENANT = True
        mock_config_class.AUTH_ENABLED = False
        app.extensions['config_class'] = mock_config_class

        mock_tenant_service = MagicMock()
        mock_tenant_service.update_tenant.side_effect = ValueError("mdm_identifier cannot be blank")
        app.extensions['tenant_service'] = mock_tenant_service

        response = client.put('/api/tenants/tenant_1', json={'mdm_identifier': ''})

        assert response.status_code == 400
        assert response.get_json()['error']['code'] == 'VALIDATION_ERROR'

    def test_update_tenant_duplicate_mdm_identifier_returns_400(self, client, app):
        """Test PUT /api/tenants/<id> surfaces an mdm_identifier collision as a
        client error, not a generic 500."""
        mock_config_class = MagicMock()
        mock_config_class.ENABLE_MULTI_TENANT = True
        mock_config_class.AUTH_ENABLED = False
        app.extensions['config_class'] = mock_config_class

        mock_tenant_service = MagicMock()
        mock_tenant_service.update_tenant.side_effect = ValueError(
            "mdm_identifier 'intune-1' is already used by another tenant"
        )
        app.extensions['tenant_service'] = mock_tenant_service

        response = client.put('/api/tenants/tenant_2', json={'mdm_identifier': 'intune-1'})

        assert response.status_code == 400
        assert response.get_json()['error']['code'] == 'VALIDATION_ERROR'

    def test_create_tenant_missing_field_returns_400(self, client, app):
        """Test POST /api/tenants returns 400 when a required field is missing"""
        mock_config_class = MagicMock()
        mock_config_class.ENABLE_MULTI_TENANT = True
        mock_config_class.AUTH_ENABLED = False
        app.extensions['config_class'] = mock_config_class
        app.extensions['tenant_service'] = MagicMock()

        response = client.post('/api/tenants', json={
            'tenant_id': 'tenant_1',
            'tenant_name': 'Company A',
            'mdm_provider': 'InTune',
            'mdm_identifier': 'intune-1'
            # lookout_application_key missing
        })

        assert response.status_code == 400
        assert response.get_json()['error']['code'] == 'VALIDATION_ERROR'

    def test_update_tenant_partial_update(self, client, app):
        """Test PUT /api/tenants/<id> sends only provided fields"""
        mock_config_class = MagicMock()
        mock_config_class.ENABLE_MULTI_TENANT = True
        mock_config_class.AUTH_ENABLED = False
        app.extensions['config_class'] = mock_config_class

        mock_tenant_service = MagicMock()
        mock_tenant = MagicMock()
        mock_tenant.to_dict.return_value = {
            'tenant_id': 'tenant_1', 'tenant_name': 'New Name', 'mdm_provider': 'InTune',
            'mdm_identifier': 'intune-1', 'description': '', 'enabled': True
        }
        mock_tenant_service.update_tenant.return_value = mock_tenant
        app.extensions['tenant_service'] = mock_tenant_service

        response = client.put('/api/tenants/tenant_1', json={'tenant_name': 'New Name'})

        assert response.status_code == 200
        mock_tenant_service.update_tenant.assert_called_once_with('tenant_1', tenant_name='New Name')

    def test_update_tenant_empty_key_does_not_pass_as_clear(self, client, app):
        """Test PUT /api/tenants/<id> forwards an empty key string as-is (service layer ignores it)"""
        mock_config_class = MagicMock()
        mock_config_class.ENABLE_MULTI_TENANT = True
        mock_config_class.AUTH_ENABLED = False
        app.extensions['config_class'] = mock_config_class

        mock_tenant_service = MagicMock()
        mock_tenant = MagicMock()
        mock_tenant.to_dict.return_value = {
            'tenant_id': 'tenant_1', 'tenant_name': 'Company A', 'mdm_provider': 'InTune',
            'mdm_identifier': 'intune-1', 'description': '', 'enabled': True
        }
        mock_tenant_service.update_tenant.return_value = mock_tenant
        app.extensions['tenant_service'] = mock_tenant_service

        response = client.put('/api/tenants/tenant_1', json={'lookout_application_key': ''})

        assert response.status_code == 200
        mock_tenant_service.update_tenant.assert_called_once_with('tenant_1', lookout_application_key='')

    def test_update_tenant_unknown_id_returns_404(self, client, app):
        """Test PUT /api/tenants/<id> returns 404 for unknown tenant"""
        mock_config_class = MagicMock()
        mock_config_class.ENABLE_MULTI_TENANT = True
        mock_config_class.AUTH_ENABLED = False
        app.extensions['config_class'] = mock_config_class

        mock_tenant_service = MagicMock()
        mock_tenant_service.update_tenant.return_value = None
        app.extensions['tenant_service'] = mock_tenant_service

        response = client.put('/api/tenants/unknown', json={'tenant_name': 'New Name'})

        assert response.status_code == 404
        assert response.get_json()['error']['code'] == 'TENANT_NOT_FOUND'

    def test_suspend_tenant_success(self, client, app):
        """Test POST /api/tenants/<id>/suspend disables the tenant"""
        mock_config_class = MagicMock()
        mock_config_class.ENABLE_MULTI_TENANT = True
        mock_config_class.AUTH_ENABLED = False
        app.extensions['config_class'] = mock_config_class

        mock_tenant_service = MagicMock()
        mock_tenant = MagicMock()
        mock_tenant.to_dict.return_value = {'tenant_id': 'tenant_1', 'enabled': False}
        mock_tenant_service.set_tenant_enabled.return_value = mock_tenant
        app.extensions['tenant_service'] = mock_tenant_service

        response = client.post('/api/tenants/tenant_1/suspend')

        assert response.status_code == 200
        mock_tenant_service.set_tenant_enabled.assert_called_once_with('tenant_1', False)

    def test_suspend_tenant_unknown_id_returns_404(self, client, app):
        mock_config_class = MagicMock()
        mock_config_class.ENABLE_MULTI_TENANT = True
        mock_config_class.AUTH_ENABLED = False
        app.extensions['config_class'] = mock_config_class

        mock_tenant_service = MagicMock()
        mock_tenant_service.set_tenant_enabled.return_value = None
        app.extensions['tenant_service'] = mock_tenant_service

        response = client.post('/api/tenants/unknown/suspend')

        assert response.status_code == 404
        assert response.get_json()['error']['code'] == 'TENANT_NOT_FOUND'

    def test_activate_tenant_success(self, client, app):
        """Test POST /api/tenants/<id>/activate enables the tenant"""
        mock_config_class = MagicMock()
        mock_config_class.ENABLE_MULTI_TENANT = True
        mock_config_class.AUTH_ENABLED = False
        app.extensions['config_class'] = mock_config_class

        mock_tenant_service = MagicMock()
        mock_tenant = MagicMock()
        mock_tenant.to_dict.return_value = {'tenant_id': 'tenant_1', 'enabled': True}
        mock_tenant_service.set_tenant_enabled.return_value = mock_tenant
        app.extensions['tenant_service'] = mock_tenant_service

        response = client.post('/api/tenants/tenant_1/activate')

        assert response.status_code == 200
        mock_tenant_service.set_tenant_enabled.assert_called_once_with('tenant_1', True)

    def test_activate_tenant_unknown_id_returns_404(self, client, app):
        mock_config_class = MagicMock()
        mock_config_class.ENABLE_MULTI_TENANT = True
        mock_config_class.AUTH_ENABLED = False
        app.extensions['config_class'] = mock_config_class

        mock_tenant_service = MagicMock()
        mock_tenant_service.set_tenant_enabled.return_value = None
        app.extensions['tenant_service'] = mock_tenant_service

        response = client.post('/api/tenants/unknown/activate')

        assert response.status_code == 404
        assert response.get_json()['error']['code'] == 'TENANT_NOT_FOUND'

    def test_purge_tenant_calls_through_to_cache_and_service(self, client, app):
        """Test POST /api/tenants/<id>/purge calls purge_tenant_devices and drop_tenant_client"""
        mock_config_class = MagicMock()
        mock_config_class.ENABLE_MULTI_TENANT = True
        mock_config_class.AUTH_ENABLED = False
        app.extensions['config_class'] = mock_config_class

        mock_tenant_service = MagicMock()
        mock_tenant_service.get_tenant_by_id.return_value = MagicMock()
        app.extensions['tenant_service'] = mock_tenant_service

        mock_cache = MagicMock()
        mock_cache.purge_tenant_devices.return_value = 7
        app.extensions['device_cache'] = mock_cache

        mock_device_service = MagicMock()
        app.extensions['device_service'] = mock_device_service

        response = client.post('/api/tenants/tenant_1/purge')

        assert response.status_code == 200
        data = response.get_json()
        assert data['purged_device_count'] == 7
        assert data['tenant_id'] == 'tenant_1'
        mock_cache.purge_tenant_devices.assert_called_once_with('tenant_1')
        mock_device_service.drop_tenant_client.assert_called_once_with('tenant_1')

    def test_purge_tenant_unknown_id_returns_404(self, client, app):
        mock_config_class = MagicMock()
        mock_config_class.ENABLE_MULTI_TENANT = True
        mock_config_class.AUTH_ENABLED = False
        app.extensions['config_class'] = mock_config_class

        mock_tenant_service = MagicMock()
        mock_tenant_service.get_tenant_by_id.return_value = None
        app.extensions['tenant_service'] = mock_tenant_service

        response = client.post('/api/tenants/unknown/purge')

        assert response.status_code == 404
        assert response.get_json()['error']['code'] == 'TENANT_NOT_FOUND'

    def test_delete_tenant_calls_purge_then_delete(self, client, app):
        """Test DELETE /api/tenants/<id> purges cached data then deletes the tenant"""
        mock_config_class = MagicMock()
        mock_config_class.ENABLE_MULTI_TENANT = True
        mock_config_class.AUTH_ENABLED = False
        app.extensions['config_class'] = mock_config_class

        mock_tenant_service = MagicMock()
        mock_tenant_service.get_tenant_by_id.return_value = MagicMock()
        app.extensions['tenant_service'] = mock_tenant_service

        mock_cache = MagicMock()
        mock_cache.purge_tenant_devices.return_value = 3
        app.extensions['device_cache'] = mock_cache

        mock_device_service = MagicMock()
        app.extensions['device_service'] = mock_device_service

        response = client.delete('/api/tenants/tenant_1')

        assert response.status_code == 200
        data = response.get_json()
        assert data['deleted_tenant_id'] == 'tenant_1'
        assert data['purged_device_count'] == 3
        mock_cache.purge_tenant_devices.assert_called_once_with('tenant_1')
        mock_device_service.drop_tenant_client.assert_called_once_with('tenant_1')
        mock_tenant_service.delete_tenant.assert_called_once_with('tenant_1')

    def test_delete_tenant_unknown_id_returns_404(self, client, app):
        mock_config_class = MagicMock()
        mock_config_class.ENABLE_MULTI_TENANT = True
        mock_config_class.AUTH_ENABLED = False
        app.extensions['config_class'] = mock_config_class

        mock_tenant_service = MagicMock()
        mock_tenant_service.get_tenant_by_id.return_value = None
        app.extensions['tenant_service'] = mock_tenant_service

        response = client.delete('/api/tenants/unknown')

        assert response.status_code == 404
        assert response.get_json()['error']['code'] == 'TENANT_NOT_FOUND'


class TestCVERoutes:
    """Test suite for CVE scanner routes"""
    
    def test_get_fleet_os_versions_returns_versions(self, client, app, sample_devices):
        """Test /api/cve/fleet/os-versions returns OS versions"""
        mock_service = MagicMock()
        mock_service.get_cached_devices.return_value = sample_devices
        app.extensions['device_service'] = mock_service
        
        response = client.get('/api/cve/fleet/os-versions')
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'android_versions' in data
        assert 'ios_versions' in data
        assert 'total_devices' in data
    
    def test_get_cve_details_validates_format(self, client, app):
        """Test /api/cve/<name> validates CVE format"""
        response = client.get('/api/cve/INVALID-CVE')
        
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
        assert 'INVALID_CVE_FORMAT' in data['error']['code']
