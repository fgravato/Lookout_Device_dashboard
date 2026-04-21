"""
Lookout Mobile Risk API v2 Client

This module provides a client for interacting with the Lookout Mobile Risk API v2,
including OAuth 2.0 authentication and device data retrieval.
"""

import os
import time
import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class LookoutAPIError(Exception):
    """Custom exception for Lookout API errors"""
    pass


class LookoutMRAClient:
    """Client for Lookout Mobile Risk API v2"""

    def __init__(self, application_key: Optional[str] = None, config: Optional[Any] = None):
        """
        Initialize the Lookout MRA client

        Args:
            application_key: The Lookout application key for OAuth authentication
            config: Optional config object with proxy settings
        """
        self.application_key = application_key or os.getenv('LOOKOUT_APPLICATION_KEY')
        if not self.application_key:
            raise LookoutAPIError("LOOKOUT_APPLICATION_KEY is required")

        self.base_url = "https://api.lookout.com"
        self.oauth_url = f"{self.base_url}/oauth2/token"
        self.devices_url = f"{self.base_url}/mra/api/v2/devices"

        self.access_token = None
        self.token_expires_at = None
        self.session = requests.Session()

        # Configure proxy settings
        self._configure_proxy(config)

        # Set default headers
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded'
        })

    def _configure_proxy(self, config: Optional[Any] = None):
        """
        Configure proxy settings for the session

        Args:
            config: Config object with proxy settings, or None to read from env
        """
        http_proxy = getattr(config, 'HTTP_PROXY', '') if config else os.getenv('HTTP_PROXY', os.getenv('http_proxy', ''))
        https_proxy = getattr(config, 'HTTPS_PROXY', '') if config else os.getenv('HTTPS_PROXY', os.getenv('https_proxy', ''))
        verify_ssl = getattr(config, 'PROXY_VERIFY_SSL', True) if config else os.getenv('PROXY_VERIFY_SSL', 'true').lower() == 'true'
        ca_bundle = getattr(config, 'PROXY_CA_BUNDLE', '') if config else os.getenv('PROXY_CA_BUNDLE', '')

        proxies = {}
        if http_proxy:
            proxies['http'] = http_proxy
        if https_proxy:
            proxies['https'] = https_proxy

        if proxies:
            self.session.proxies.update(proxies)
            logger.info(f"Proxy configured: HTTP={http_proxy or 'none'}, HTTPS={https_proxy or 'none'}")

        # SSL verification settings
        if ca_bundle:
            self.session.verify = ca_bundle
            logger.info(f"Using custom CA bundle: {ca_bundle}")
        elif not verify_ssl:
            self.session.verify = False
            logger.warning("SSL verification disabled - not recommended for production")
    
    def _is_token_valid(self) -> bool:
        """Check if the current access token is valid and not expired"""
        if not self.access_token or not self.token_expires_at:
            return False
        
        # Add 5 minute buffer before expiration
        buffer_time = datetime.now() + timedelta(minutes=5)
        return buffer_time < self.token_expires_at
    
    def authenticate(self) -> bool:
        """
        Authenticate with the Lookout API using OAuth 2.0 Client Credentials flow
        
        Returns:
            bool: True if authentication successful, False otherwise
        """
        try:
            headers = {
                'Authorization': f'Bearer {self.application_key}',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json'
            }
            
            data = {
                'grant_type': 'client_credentials'
            }
            
            logger.info("Requesting OAuth token from Lookout API")
            response = self.session.post(self.oauth_url, headers=headers, data=data, timeout=30)
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data['access_token']
                
                # Calculate expiration time
                expires_in = token_data.get('expires_in', 7200)  # Default 2 hours
                self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)
                
                # Update session headers with new token
                self.session.headers.update({
                    'Authorization': f'Bearer {self.access_token}'
                })
                
                logger.info(f"Successfully authenticated. Token expires at {self.token_expires_at}")
                return True
            else:
                logger.error(f"Authentication failed: {response.status_code} - {response.text}")
                raise LookoutAPIError(f"Authentication failed: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during authentication: {e}")
            raise LookoutAPIError(f"Network error during authentication: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during authentication: {e}")
            raise LookoutAPIError(f"Authentication error: {e}")
    
    def is_authenticated(self) -> bool:
        """Check if the client is currently authenticated with a valid token"""
        return self._is_token_valid()
    
    def _ensure_authenticated(self):
        """Ensure the client is authenticated, re-authenticate if necessary"""
        if not self._is_token_valid():
            logger.info("Token expired or invalid, re-authenticating")
            self.authenticate()
    
    def get_devices(self, limit: int = 100, **filters) -> List[Dict[str, Any]]:
        """
        Retrieve devices from the Lookout API
        
        Args:
            limit: Maximum number of devices to retrieve (max 1000)
            **filters: Additional filters for the API request
        
        Returns:
            List of device dictionaries
        """
        self._ensure_authenticated()
        
        try:
            params = {
                'limit': min(limit, 1000)  # API max is 1000
            }
            
            # Add any additional filters
            params.update(filters)
            
            logger.info(f"Fetching devices with params: {params}")
            response = self.session.get(self.devices_url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                devices = data.get('devices', [])
                logger.info(f"Successfully retrieved {len(devices)} devices")
                return devices
            elif response.status_code == 401:
                logger.warning("Received 401, re-authenticating and retrying")
                self.authenticate()
                response = self.session.get(self.devices_url, params=params, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    devices = data.get('devices', [])
                    logger.info(f"Successfully retrieved {len(devices)} devices after re-auth")
                    return devices
                else:
                    raise LookoutAPIError(f"API request failed after re-auth: {response.status_code}")
            elif response.status_code == 429:
                logger.warning("Rate limited, waiting before retry")
                time.sleep(5)
                raise LookoutAPIError("Rate limited - please try again later")
            else:
                logger.error(f"API request failed: {response.status_code} - {response.text}")
                raise LookoutAPIError(f"API request failed: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during device fetch: {e}")
            raise LookoutAPIError(f"Network error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during device fetch: {e}")
            raise LookoutAPIError(f"Device fetch error: {e}")

    def get_devices_by_cve(self, cve_name: str) -> Dict[str, Any]:
        """
        Retrieve devices vulnerable to a specific CVE

        Args:
            cve_name: CVE identifier (e.g., "CVE-2022-36934")

        Returns:
            Dictionary containing count and list of vulnerable devices
        """
        self._ensure_authenticated()

        try:
            url = f"{self.base_url}/mra/api/v2/os-vulns/devices"
            params = {
                'name': cve_name
            }

            logger.info(f"Fetching devices vulnerable to {cve_name}")
            response = self.session.get(url, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                logger.info(f"Successfully retrieved {data.get('count', 0)} devices vulnerable to {cve_name}")
                return data
            elif response.status_code == 401:
                logger.warning("Received 401, re-authenticating and retrying")
                self.authenticate()
                response = self.session.get(url, params=params, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Successfully retrieved {data.get('count', 0)} devices vulnerable to {cve_name} after re-auth")
                    return data
                else:
                    raise LookoutAPIError(f"API request failed after re-auth: {response.status_code}")
            else:
                logger.error(f"API request failed: {response.status_code} - {response.text}")
                raise LookoutAPIError(f"API request failed: {response.status_code}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during CVE device fetch: {e}")
            raise LookoutAPIError(f"Network error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during CVE device fetch: {e}")
            raise LookoutAPIError(f"CVE device fetch error: {e}")
    
    def get_fleet_os_versions(self) -> Dict[str, Any]:
        """
        Get all distinct OS versions in the fleet
        
        Returns:
            Dictionary with Android and iOS versions
        """
        self._ensure_authenticated()
        
        try:
            url = f"{self.base_url}/mra/api/v2/os-vulns/os-versions"
            logger.info("Fetching fleet OS versions")
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                logger.info("Successfully retrieved OS versions")
                return data
            elif response.status_code == 401:
                logger.warning("Received 401, re-authenticating and retrying")
                self.authenticate()
                response = self.session.get(url, timeout=30)
                if response.status_code == 200:
                    return response.json()
                else:
                    raise LookoutAPIError(f"API request failed after re-auth: {response.status_code}")
            else:
                logger.error(f"API request failed: {response.status_code} - {response.text}")
                raise LookoutAPIError(f"API request failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Unexpected error during OS versions fetch: {e}")
            raise LookoutAPIError(f"OS versions fetch error: {e}")
    
    def get_android_vulnerabilities(self, aspl: str, min_severity: Optional[int] = None) -> Dict[str, Any]:
        """
        Get vulnerabilities for a specific Android Security Patch Level
        
        Args:
            aspl: Android Security Patch Level (e.g., "2024-01-01")
            min_severity: Minimum severity (0-10), optional
            
        Returns:
            Dictionary with vulnerabilities
        """
        self._ensure_authenticated()
        
        try:
            url = f"{self.base_url}/mra/api/v2/os-vulns/android"
            params = {'aspl': aspl}
            if min_severity is not None:
                params['severity'] = min_severity
            
            logger.info(f"Fetching Android vulnerabilities for {aspl}")
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                self.authenticate()
                response = self.session.get(url, params=params, timeout=30)
                if response.status_code == 200:
                    return response.json()
                else:
                    raise LookoutAPIError(f"API request failed after re-auth: {response.status_code}")
            else:
                logger.error(f"API request failed: {response.status_code} - {response.text}")
                raise LookoutAPIError(f"API request failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise LookoutAPIError(f"Android vulnerabilities fetch error: {e}")
    
    def get_ios_vulnerabilities(self, version: str, min_severity: Optional[int] = None) -> Dict[str, Any]:
        """
        Get vulnerabilities for a specific iOS version
        
        Args:
            version: iOS version (e.g., "17.2.1")
            min_severity: Minimum severity (0-10), optional
            
        Returns:
            Dictionary with vulnerabilities
        """
        self._ensure_authenticated()
        
        try:
            url = f"{self.base_url}/mra/api/v2/os-vulns/ios"
            params = {'version': version}
            if min_severity is not None:
                params['severity'] = min_severity
            
            logger.info(f"Fetching iOS vulnerabilities for {version}")
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                self.authenticate()
                response = self.session.get(url, params=params, timeout=30)
                if response.status_code == 200:
                    return response.json()
                else:
                    raise LookoutAPIError(f"API request failed after re-auth: {response.status_code}")
            else:
                logger.error(f"API request failed: {response.status_code} - {response.text}")
                raise LookoutAPIError(f"API request failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise LookoutAPIError(f"iOS vulnerabilities fetch error: {e}")
    
    def get_cve_info(self, cve_name: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific CVE
        
        Args:
            cve_name: CVE identifier (e.g., "CVE-2024-12345")
            
        Returns:
            CVE information dictionary
        """
        self._ensure_authenticated()
        
        try:
            url = f"{self.base_url}/mra/api/v2/os-vulns/cve"
            params = {'name': cve_name}
            
            logger.info(f"Fetching CVE info for {cve_name}")
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                self.authenticate()
                response = self.session.get(url, params=params, timeout=30)
                if response.status_code == 200:
                    return response.json()
                else:
                    raise LookoutAPIError(f"API request failed after re-auth: {response.status_code}")
            else:
                logger.error(f"API request failed: {response.status_code} - {response.text}")
                raise LookoutAPIError(f"API request failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise LookoutAPIError(f"CVE info fetch error: {e}")
    
    def get_device_by_id(self, device_id: str, **filters) -> Optional[Dict[str, Any]]:
        """
        Retrieve a single device by ID
        
        Args:
            device_id: The device ID to search for
            **filters: Additional filters for the API request
        
        Returns:
            Device dictionary or None if not found
        """
        self._ensure_authenticated()
        
        try:
            device_url = f"{self.base_url}/mra/api/v2/device"
            params = {
                'guid': device_id
            }
            params.update(filters)
            
            logger.info(f"Fetching device {device_id}")
            response = self.session.get(device_url, params=params, timeout=30)
            
            if response.status_code == 200:
                device = response.json()
                logger.info(f"Successfully retrieved device {device_id}")
                return device
            elif response.status_code == 404:
                logger.warning(f"Device {device_id} not found")
                return None
            elif response.status_code == 401:
                logger.warning("Received 401, re-authenticating and retrying")
                self.authenticate()
                response = self.session.get(device_url, params=params, timeout=30)
                if response.status_code == 200:
                    device = response.json()
                    logger.info(f"Successfully retrieved device {device_id} after re-auth")
                    return device
                else:
                    raise LookoutAPIError(f"API request failed after re-auth: {response.status_code}")
            else:
                logger.error(f"API request failed: {response.status_code} - {response.text}")
                raise LookoutAPIError(f"API request failed: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during device fetch: {e}")
            raise LookoutAPIError(f"Network error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during device fetch: {e}")
            raise LookoutAPIError(f"Device fetch error: {e}")