"""
Tests for the AuthManager class.
"""

import os
import json
import pytest
from unittest.mock import MagicMock, patch, mock_open
from werkzeug.security import generate_password_hash, check_password_hash

from auth import AuthManager


class TestAuthManager:
    """Test suite for AuthManager"""
    
    def test_auth_manager_init_with_demo_users(self):
        """Test AuthManager initializes with demo users in non-production mode"""
        config = MagicMock()
        config.AUTH_USERS_FILE = None
        config.AUTH_USERS = None
        
        with patch.dict(os.environ, {'FLASK_ENV': 'development'}):
            auth_manager = AuthManager(config)
        
        assert 'admin' in auth_manager.users
        assert 'user' in auth_manager.users
        assert auth_manager.check_auth('admin', 'admin123')
        assert auth_manager.check_auth('user', 'user123')
    
    def test_auth_manager_init_no_users_in_production(self):
        """Test AuthManager initializes with no users in production mode"""
        config = MagicMock()
        config.AUTH_USERS_FILE = None
        config.AUTH_USERS = None
        
        with patch.dict(os.environ, {'FLASK_ENV': 'production'}):
            auth_manager = AuthManager(config)
        
        assert len(auth_manager.users) == 0
    
    def test_auth_manager_load_from_file(self, tmp_path):
        """Test loading users from JSON file"""
        config = MagicMock()
        config.AUTH_USERS = None
        
        # Create a temp auth file
        auth_file = tmp_path / "auth_users.json"
        test_users = {
            "testuser": generate_password_hash("testpass", method='pbkdf2:sha256')
        }
        auth_file.write_text(json.dumps(test_users))
        config.AUTH_USERS_FILE = str(auth_file)
        
        auth_manager = AuthManager(config)
        
        assert 'testuser' in auth_manager.users
        assert auth_manager.check_auth('testuser', 'testpass')
    
    def test_auth_manager_load_from_env_json(self):
        """Test loading users from AUTH_USERS env var as JSON"""
        config = MagicMock()
        config.AUTH_USERS_FILE = None
        config.AUTH_USERS = json.dumps({
            "envuser": generate_password_hash("envpass", method='pbkdf2:sha256')
        })
        
        auth_manager = AuthManager(config)
        
        assert 'envuser' in auth_manager.users
        assert auth_manager.check_auth('envuser', 'envpass')
    
    def test_auth_manager_load_from_env_simple(self):
        """Test loading users from AUTH_USERS env var in simple format"""
        config = MagicMock()
        config.AUTH_USERS_FILE = None
        config.AUTH_USERS = "user1:pass1,user2:pass2"
        
        auth_manager = AuthManager(config)
        
        assert 'user1' in auth_manager.users
        assert 'user2' in auth_manager.users
        assert auth_manager.check_auth('user1', 'pass1')
        assert auth_manager.check_auth('user2', 'pass2')
    
    def test_auth_manager_plaintext_passwords(self, tmp_path):
        """Test loading users with plaintext password prefix"""
        config = MagicMock()
        config.AUTH_USERS = None
        
        auth_file = tmp_path / "auth_users.json"
        test_users = {
            "plainuser": "plaintext:plainpass"
        }
        auth_file.write_text(json.dumps(test_users))
        config.AUTH_USERS_FILE = str(auth_file)
        
        auth_manager = AuthManager(config)
        
        assert 'plainuser' in auth_manager.users
        assert auth_manager.check_auth('plainuser', 'plainpass')
    
    def test_check_auth_invalid_credentials(self):
        """Test authentication with invalid credentials"""
        config = MagicMock()
        config.AUTH_USERS_FILE = None
        config.AUTH_USERS = None
        
        with patch.dict(os.environ, {'FLASK_ENV': 'development'}):
            auth_manager = AuthManager(config)
        
        assert not auth_manager.check_auth('admin', 'wrongpassword')
        assert not auth_manager.check_auth('nonexistent', 'password')
    
    def test_requires_auth_decorator_skips_when_auth_disabled(self, app):
        """Test that requires_auth skips when AUTH_ENABLED is False"""
        config = MagicMock()
        config.AUTH_ENABLED = False
        config.AUTH_USERS_FILE = None
        config.AUTH_USERS = None
        
        with patch.dict(os.environ, {'FLASK_ENV': 'development'}):
            auth_manager = AuthManager(config)
        
        # Create a mock function to decorate
        mock_func = MagicMock(return_value='success')
        decorated = auth_manager.requires_auth(mock_func)
        
        # Use Flask test request context
        with app.test_request_context():
            result = decorated()
            
            assert result == 'success'
            mock_func.assert_called_once()
