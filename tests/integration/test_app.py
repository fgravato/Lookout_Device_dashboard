"""
Integration tests for the Flask application factory.
"""

import pytest
from unittest.mock import MagicMock, patch

from services.tenant_service import Tenant


class TestAppFactory:
    """Test suite for application factory"""
    
    def test_create_app_returns_flask_app(self, app):
        """Test create_app returns a Flask application"""
        from flask import Flask
        assert isinstance(app, Flask)
    
    def test_app_has_required_extensions(self, app):
        """Test app has all required extensions initialized"""
        required_extensions = [
            'config_class',
            'auth_manager',
            'device_cache',
            'device_service',
            'export_service',
        ]
        
        for ext in required_extensions:
            assert ext in app.extensions, f"Extension {ext} not found"
    
    def test_app_testing_config(self, app):
        """Test app uses testing configuration"""
        assert app.config['TESTING'] == True
        assert app.config['DEBUG'] == True


class TestErrorHandlers:
    """Test suite for error handlers"""
    
    def test_404_error_returns_json(self, client):
        """Test 404 errors return JSON response"""
        response = client.get('/nonexistent-route')
        
        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data
        assert data['error']['code'] == 'NOT_FOUND'
    
    def test_401_error_returns_json(self, client):
        """Test 401 errors return JSON response"""
        # Enable auth via the extensions config_class (which require_auth reads)
        original_config = client.application.extensions['config_class']
        mock_config = MagicMock(wraps=original_config)
        mock_config.AUTH_ENABLED = True
        client.application.extensions['config_class'] = mock_config
        try:
            response = client.get('/api/devices')

            # Should get 401 since no auth provided
            assert response.status_code == 401
            data = response.get_json()
            assert 'error' in data
            assert data['error']['code'] == 'AUTH_REQUIRED'
        finally:
            client.application.extensions['config_class'] = original_config


class TestAppConfiguration:
    """Test suite for app configuration"""
    
    def test_config_validation_on_startup(self):
        """Test config validation runs on app creation"""
        # Must patch in the app module's namespace since app.py uses
        # 'from config import get_config'
        with patch('app.get_config') as mock_get_config:
            mock_config = MagicMock()
            mock_config.validate_config.return_value = ['Issue 1', 'Issue 2']
            mock_config.TESTING = True
            mock_config.AUTH_ENABLED = False
            mock_config.CACHE_ENABLED = False
            mock_config.USE_SAMPLE_DATA = True
            mock_config.SECRET_KEY = 'test'
            mock_config.CACHE_MAX_AGE_MINUTES = 60
            mock_config.BACKGROUND_REFRESH_ENABLED = False
            mock_config.AUTO_REFRESH_ON_STARTUP = False
            mock_config.ENABLE_DISK_CACHE = False
            mock_config.CACHE_FILE_PATH = None
            mock_config.ENABLE_MULTI_TENANT = False
            mock_config.LOG_LEVEL = 'INFO'
            mock_config.LOG_FILE = None
            mock_get_config.return_value = mock_config

            from app import create_app
            app = create_app('testing')

            # Config validation should have been called
            mock_config.validate_config.assert_called_once()

    def test_cve_service_available_in_multi_tenant_mode_without_global_key(self, monkeypatch):
        """Multi-tenant deployments have no global LOOKOUT_APPLICATION_KEY (per-tenant
        keys live in tenants.json instead). LookoutMRAClient.__init__ raises when
        neither an explicit application_key nor the env var is set, so this only
        proves the fix if the real __init__ validation runs (not mocked away) -
        cve_service must still be constructed using a tenant's client, not left None."""
        monkeypatch.delenv('LOOKOUT_APPLICATION_KEY', raising=False)

        from lookout_client import LookoutMRAClient

        with patch('app.get_config') as mock_get_config, \
             patch('app.TenantService') as mock_tenant_service_cls, \
             patch.object(LookoutMRAClient, 'authenticate', return_value=None), \
             patch.object(LookoutMRAClient, 'is_authenticated', return_value=True):

            mock_config = MagicMock()
            mock_config.validate_config.return_value = []
            mock_config.TESTING = True
            mock_config.AUTH_ENABLED = False
            mock_config.CACHE_ENABLED = False
            mock_config.USE_SAMPLE_DATA = False
            mock_config.SECRET_KEY = 'test'
            mock_config.CACHE_MAX_AGE_MINUTES = 60
            mock_config.BACKGROUND_REFRESH_ENABLED = False
            mock_config.AUTO_REFRESH_ON_STARTUP = False
            mock_config.ENABLE_DISK_CACHE = False
            mock_config.CACHE_FILE_PATH = None
            mock_config.ENABLE_MULTI_TENANT = True
            mock_config.LOOKOUT_APPLICATION_KEY = None
            mock_config.LOG_LEVEL = 'INFO'
            mock_config.LOG_FILE = None
            mock_get_config.return_value = mock_config

            tenant = Tenant(
                tenant_id='tenant_1', tenant_name='Company A', mdm_provider='InTune',
                mdm_identifier='intune-a', lookout_application_key='tenant-key', enabled=True
            )
            mock_tenant_service = MagicMock()
            mock_tenant_service.tenants = [tenant]
            mock_tenant_service.get_all_tenants.return_value = [tenant]
            mock_tenant_service_cls.return_value = mock_tenant_service

            from app import create_app
            app = create_app('testing')

            assert app.extensions['cve_service'] is not None
