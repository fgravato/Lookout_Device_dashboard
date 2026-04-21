"""
Configuration settings for Lookout MRA Desktop Dashboard
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Base configuration class"""
    
    # Flask settings
    SECRET_KEY = os.getenv('SECRET_KEY', os.urandom(32).hex())
    DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
    
    # Authentication settings
    # Set AUTH_ENABLED=false to disable authentication (recommended for local desktop use)
    AUTH_ENABLED = os.getenv('AUTH_ENABLED', 'false').lower() == 'true'
    
    # Format: JSON dict like {"admin": "password_hash", "user": "password_hash"}
    # Or simple format: "admin:password,user:password" (will be hashed at startup)
    AUTH_USERS = os.getenv('AUTH_USERS', '')
    AUTH_USERS_FILE = os.getenv('AUTH_USERS_FILE', '')
    
    # Lookout API settings (single tenant - legacy)
    LOOKOUT_APPLICATION_KEY = os.getenv('LOOKOUT_APPLICATION_KEY')
    USE_SAMPLE_DATA = os.getenv('USE_SAMPLE_DATA', 'false').lower() == 'true'
    
    # Multi-tenant configuration
    ENABLE_MULTI_TENANT = os.getenv('ENABLE_MULTI_TENANT', 'false').lower() == 'true'
    TENANTS_CONFIG_FILE = os.getenv('TENANTS_CONFIG_FILE', './tenants.json')
    
    # Cache settings
    CACHE_ENABLED = os.getenv('CACHE_ENABLED', 'true').lower() == 'true'
    CACHE_MAX_AGE_MINUTES = int(os.getenv('CACHE_MAX_AGE_MINUTES', '60'))
    
    # API settings
    API_TIMEOUT = int(os.getenv('API_TIMEOUT', '30'))
    API_RETRY_ATTEMPTS = int(os.getenv('API_RETRY_ATTEMPTS', '3'))
    MAX_DEVICES_PER_REQUEST = int(os.getenv('MAX_DEVICES_PER_REQUEST', '1000'))
    
    # Delta sync settings
    ENABLE_DELTA_SYNC = os.getenv('ENABLE_DELTA_SYNC', 'true').lower() == 'true'
    DELTA_SYNC_LOOKBACK_HOURS = int(os.getenv('DELTA_SYNC_LOOKBACK_HOURS', '24'))
    
    # Optional persistence settings
    ENABLE_DISK_CACHE = os.getenv('ENABLE_DISK_CACHE', 'true').lower() == 'true'
    CACHE_FILE_PATH = os.getenv('CACHE_FILE_PATH', './device_cache.db')
    
    # Auto-refresh settings
    AUTO_REFRESH_ON_STARTUP = os.getenv('AUTO_REFRESH_ON_STARTUP', 'true').lower() == 'true'
    BACKGROUND_REFRESH_ENABLED = os.getenv('BACKGROUND_REFRESH_ENABLED', 'false').lower() == 'true'
    BACKGROUND_REFRESH_INTERVAL_MINUTES = int(os.getenv('BACKGROUND_REFRESH_INTERVAL_MINUTES', '30'))
    
    # Logging settings
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
    LOG_FILE = os.getenv('LOG_FILE', None)  # None means console only
    
    # Server settings
    HOST = os.getenv('HOST', '127.0.0.1')  # Localhost for desktop
    PORT = int(os.getenv('PORT', '5001'))

    # Proxy settings (for secure environments)
    HTTP_PROXY = os.getenv('HTTP_PROXY', os.getenv('http_proxy', ''))
    HTTPS_PROXY = os.getenv('HTTPS_PROXY', os.getenv('https_proxy', ''))
    NO_PROXY = os.getenv('NO_PROXY', os.getenv('no_proxy', ''))
    PROXY_VERIFY_SSL = os.getenv('PROXY_VERIFY_SSL', 'true').lower() == 'true'
    PROXY_CA_BUNDLE = os.getenv('PROXY_CA_BUNDLE', '')  # Path to CA cert bundle for proxy

    # Performance settings
    ENABLE_THREADING = os.getenv('ENABLE_THREADING', 'true').lower() == 'true'
    
    @classmethod
    def validate_config(cls):
        """Validate configuration and return any issues"""
        issues = []
        
        # Security: Check SECRET_KEY in production
        flask_env = os.getenv('FLASK_ENV', 'development')
        if flask_env == 'production':
            if not os.getenv('SECRET_KEY'):
                issues.append("CRITICAL: SECRET_KEY should be explicitly set in production (via SECRET_KEY env var)")
            if not cls.AUTH_USERS and not cls.AUTH_USERS_FILE:
                issues.append("WARNING: No AUTH_USERS or AUTH_USERS_FILE configured - using demo credentials")
        
        if cls.ENABLE_MULTI_TENANT:
            if not os.path.isfile(cls.TENANTS_CONFIG_FILE):
                issues.append(f"TENANTS_CONFIG_FILE '{cls.TENANTS_CONFIG_FILE}' not found when ENABLE_MULTI_TENANT is enabled")
        elif not cls.USE_SAMPLE_DATA and not cls.LOOKOUT_APPLICATION_KEY:
            issues.append("LOOKOUT_APPLICATION_KEY is required when not using sample data or multi-tenant mode")
        
        if cls.CACHE_MAX_AGE_MINUTES < 1:
            issues.append("CACHE_MAX_AGE_MINUTES must be at least 1 minute")
        
        if cls.MAX_DEVICES_PER_REQUEST > 1000:
            issues.append("MAX_DEVICES_PER_REQUEST cannot exceed 1000 (API limit)")
        
        if cls.ENABLE_DISK_CACHE and not cls.CACHE_FILE_PATH:
            issues.append("CACHE_FILE_PATH is required when ENABLE_DISK_CACHE is true")
        
        return issues
    
    @classmethod
    def get_summary(cls):
        """Get a summary of current configuration"""
        return {
            'mode': 'Sample Data' if cls.USE_SAMPLE_DATA else 'Production API',
            'cache_enabled': cls.CACHE_ENABLED,
            'cache_max_age_minutes': cls.CACHE_MAX_AGE_MINUTES,
            'disk_cache_enabled': cls.ENABLE_DISK_CACHE,
            'delta_sync_enabled': cls.ENABLE_DELTA_SYNC,
            'api_timeout': cls.API_TIMEOUT,
            'max_devices_per_request': cls.MAX_DEVICES_PER_REQUEST,
            'host': cls.HOST,
            'port': cls.PORT,
            'debug': cls.DEBUG,
            'proxy_configured': bool(cls.HTTPS_PROXY or cls.HTTP_PROXY)
        }


class DevelopmentConfig(Config):
    """Development configuration - only overrides if not set in .env"""
    DEBUG = True if not os.getenv('DEBUG') else Config.DEBUG
    CACHE_MAX_AGE_MINUTES = 5 if not os.getenv('CACHE_MAX_AGE_MINUTES') else Config.CACHE_MAX_AGE_MINUTES
    LOG_LEVEL = 'DEBUG' if not os.getenv('LOG_LEVEL') else Config.LOG_LEVEL


class ProductionConfig(Config):
    """Production configuration - only overrides if not set in .env"""
    DEBUG = False if not os.getenv('DEBUG') else Config.DEBUG
    CACHE_MAX_AGE_MINUTES = 60 if not os.getenv('CACHE_MAX_AGE_MINUTES') else Config.CACHE_MAX_AGE_MINUTES
    LOG_LEVEL = 'INFO' if not os.getenv('LOG_LEVEL') else Config.LOG_LEVEL
    ENABLE_DISK_CACHE = True if not os.getenv('ENABLE_DISK_CACHE') else Config.ENABLE_DISK_CACHE


class TestingConfig(Config):
    """Testing configuration - only overrides if not set in .env"""
    DEBUG = True if not os.getenv('DEBUG') else Config.DEBUG
    CACHE_ENABLED = False if not os.getenv('CACHE_ENABLED') else Config.CACHE_ENABLED
    LOG_LEVEL = 'WARNING' if not os.getenv('LOG_LEVEL') else Config.LOG_LEVEL


# Configuration mapping
config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': Config  # Use base Config class as default to respect .env
}


def get_config(config_name=None):
    """Get configuration class based on environment"""
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'default')
    
    return config_map.get(config_name, Config)  # Default to base Config class


def print_config_summary():
    """Print current configuration summary"""
    config_class = get_config()
    summary = config_class.get_summary()
    
    print("\n" + "="*50)
    print("LOOKOUT MRA DASHBOARD CONFIGURATION")
    print("="*50)
    
    for key, value in summary.items():
        print(f"{key.replace('_', ' ').title()}: {value}")
    
    # Validate configuration
    issues = config_class.validate_config()
    if issues:
        print("\n⚠️  CONFIGURATION ISSUES:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\n✅ Configuration is valid")
    
    print("="*50 + "\n")


if __name__ == '__main__':
    # Print configuration when run directly
    print_config_summary()