"""
Test fixtures and configuration for the Lookout Dashboard test suite.
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from config import Config


class TestConfig(Config):
    """Test configuration with mocked settings"""
    TESTING = True
    DEBUG = True
    USE_SAMPLE_DATA = True
    AUTH_ENABLED = False
    CACHE_ENABLED = False
    SECRET_KEY = 'test-secret-key'
    CACHE_MAX_AGE_MINUTES = 60
    BACKGROUND_REFRESH_ENABLED = False
    AUTO_REFRESH_ON_STARTUP = False


@pytest.fixture
def app():
    """Create application for testing"""
    app = create_app('testing')
    app.config.from_object(TestConfig)
    
    # Initialize extensions for testing
    app.extensions = {
        'config_class': TestConfig,
        'auth_manager': MagicMock(),
        'device_cache': MagicMock(),
        'device_service': MagicMock(),
        'export_service': MagicMock(),
        'cve_service': None,
        'tenant_service': None,
    }
    
    # Mock auth manager to always return True
    app.extensions['auth_manager'].check_auth.return_value = True
    
    yield app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create test CLI runner"""
    return app.test_cli_runner()


# Sample device data fixtures
@pytest.fixture
def sample_device():
    """Single sample device"""
    return {
        'device_id': 'test-device-001',
        'device_name': 'Test iPhone',
        'user_email': 'test@example.com',
        'platform': 'iOS',
        'os_version': '16.5',
        'risk_level': 'Low',
        'compliance_status': 'Compliant',
        'last_checkin': '2024-01-15T10:30:00Z',
        'days_since_checkin': 2,
        'security_patch_level': 'N/A',
        'app_version': '1.2.3',
        'device_group_name': 'Test Group',
        'mdm_id': 'mdm-001',
        'manufacturer': 'Apple',
        'model': 'iPhone 14',
        'activation_status': 'Activated',
        'threat_family_names': [],
        'threat_descriptions': [],
        'mdm_provider': 'Test MDM',
        'mdm_identifier': 'test-mdm-001',
        'tenant_id': 'tenant-001',
        'tenant_name': 'Test Tenant',
    }


@pytest.fixture
def sample_devices():
    """List of sample devices for testing"""
    return [
        {
            'device_id': 'device-001',
            'device_name': 'iPhone 1',
            'user_email': 'user1@example.com',
            'platform': 'iOS',
            'os_version': '16.5',
            'risk_level': 'Critical',
            'compliance_status': 'Non-Compliant',
            'last_checkin': '2024-01-15T10:30:00Z',
            'days_since_checkin': 1,
        },
        {
            'device_id': 'device-002',
            'device_name': 'Android Phone',
            'user_email': 'user2@example.com',
            'platform': 'Android',
            'os_version': '13',
            'risk_level': 'High',
            'compliance_status': 'Compliant',
            'last_checkin': '2024-01-10T08:00:00Z',
            'days_since_checkin': 7,
            'security_patch_level': '2024-01-01',
        },
        {
            'device_id': 'device-003',
            'device_name': 'Secure iPad',
            'user_email': 'user3@example.com',
            'platform': 'iOS',
            'os_version': '17.0',
            'risk_level': 'Secure',
            'compliance_status': 'Compliant',
            'last_checkin': '2024-01-14T15:00:00Z',
            'days_since_checkin': 3,
        },
    ]


@pytest.fixture
def mock_config():
    """Mock configuration object"""
    config = MagicMock()
    config.USE_SAMPLE_DATA = True
    config.AUTH_ENABLED = False
    config.CACHE_ENABLED = False
    config.CACHE_MAX_AGE_MINUTES = 60
    config.SECRET_KEY = 'test-secret'
    config.AUTH_USERS = None
    config.AUTH_USERS_FILE = None
    return config
