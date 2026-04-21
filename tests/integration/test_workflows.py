"""
End-to-end tests for critical user workflows.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestDeviceWorkflow:
    """Test complete device management workflow"""
    
    def test_full_device_lifecycle(self, client, app, sample_devices):
        """Test viewing devices, getting details, and exporting"""
        # Setup mocks
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
        
        # Step 1: Get device list
        response = client.get('/api/devices')
        assert response.status_code == 200
        data = response.get_json()
        assert data['total_count'] == 3
        
        # Step 2: Get specific device details
        device_id = sample_devices[0]['device_id']
        response = client.get(f'/api/device/{device_id}')
        assert response.status_code == 200
        
        # Step 3: Get device groups
        response = client.get('/api/devices/groups')
        assert response.status_code == 200
        data = response.get_json()
        assert 'groups' in data
        assert 'counts' in data


class TestExportWorkflow:
    """Test export functionality workflow"""
    
    def test_export_device_data(self, client, app, sample_devices):
        """Test exporting device data in different formats"""
        # Setup mocks
        mock_service = MagicMock()
        mock_service.get_cached_devices.return_value = sample_devices
        app.extensions['device_service'] = mock_service
        
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
            tmp.write(b'fake excel content')
            tmp_path = tmp.name
        
        mock_export = MagicMock()
        mock_export.export_devices_to_excel.return_value = tmp_path
        app.extensions['export_service'] = mock_export
        
        # Test Excel export
        with patch('routes.export.send_file') as mock_send:
            mock_send.return_value = 'excel file'
            response = client.get('/api/export/excel')
            mock_send.assert_called_once()
        
        # Cleanup
        import os
        os.unlink(tmp_path)


class TestCacheWorkflow:
    """Test cache management workflow"""
    
    def test_cache_refresh_workflow(self, client, app, sample_devices):
        """Test checking stats, refreshing, and clearing cache"""
        # Setup mocks
        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = {
            'cached_devices': 100,
            'cache_age_minutes': 5,
            'last_sync_time': '2024-01-15T10:00:00Z'
        }
        app.extensions['device_cache'] = mock_cache
        
        mock_service = MagicMock()
        mock_service.fetch_and_cache_devices.return_value = sample_devices
        app.extensions['device_service'] = mock_service
        
        # Step 1: Check cache stats
        response = client.get('/api/cache/stats')
        assert response.status_code == 200
        data = response.get_json()
        assert data['cached_devices'] == 100
        
        # Step 2: Refresh cache
        response = client.get('/api/refresh')
        assert response.status_code == 200
        mock_service.fetch_and_cache_devices.assert_called_once()
        
        # Step 3: Clear cache
        response = client.get('/api/cache/clear')
        assert response.status_code == 200
        mock_cache.clear.assert_called_once()
