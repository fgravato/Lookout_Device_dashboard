"""
Authentication Manager for the Lookout Dashboard.

Handles user authentication with support for file-based and environment-based credentials.
"""

import os
import json
import logging
from typing import Dict

from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger(__name__)


class AuthManager:
    """Manages user authentication with users from environment/config"""
    
    def __init__(self, config_class):
        self.config = config_class
        self.users: Dict[str, str] = {}
        self._load_users()
    
    def _load_users(self):
        """Load users from config/environment"""
        if self.config.AUTH_USERS_FILE:
            try:
                if os.path.isfile(self.config.AUTH_USERS_FILE):
                    with open(self.config.AUTH_USERS_FILE, 'r') as f:
                        user_data = json.load(f)
                        for username, password in user_data.items():
                            if password.startswith('plaintext:'):
                                self.users[username] = generate_password_hash(password[10:], method='pbkdf2:sha256')
                            else:
                                self.users[username] = password
                    logger.info(f"Loaded {len(self.users)} users from file: {self.config.AUTH_USERS_FILE}")
                    return
            except Exception as e:
                logger.error(f"Failed to load users from file: {e}")
        
        if self.config.AUTH_USERS:
            try:
                if self.config.AUTH_USERS.startswith('{'):
                    user_data = json.loads(self.config.AUTH_USERS)
                    for username, password in user_data.items():
                        if password.startswith('plaintext:'):
                            self.users[username] = generate_password_hash(password[10:], method='pbkdf2:sha256')
                        else:
                            self.users[username] = password
                else:
                    for user_entry in self.config.AUTH_USERS.split(','):
                        if ':' in user_entry:
                            username, password = user_entry.strip().split(':', 1)
                            self.users[username] = generate_password_hash(password, method='pbkdf2:sha256')
                logger.info(f"Loaded {len(self.users)} users from AUTH_USERS env var")
                return
            except Exception as e:
                logger.error(f"Failed to parse AUTH_USERS: {e}")
        
        flask_env = os.getenv('FLASK_ENV', 'development')
        if flask_env != 'production':
            logger.warning("Using demo credentials - NOT FOR PRODUCTION USE")
            self.users = {
                "admin": generate_password_hash("admin123", method='pbkdf2:sha256'),
                "user": generate_password_hash("user123", method='pbkdf2:sha256')
            }
        else:
            logger.error("No users configured in production mode!")
            self.users = {}
    
    def check_auth(self, username: str, password: str) -> bool:
        """Validate username and password"""
        user_hash = self.users.get(username)
        if user_hash and check_password_hash(user_hash, password):
            return True
        return False
    
