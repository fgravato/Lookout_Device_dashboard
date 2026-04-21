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
        
        response = client.get('/api/cache/clear')
        
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
        
        # Cleanup
        import os
        os.unlink(tmp_path)


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
