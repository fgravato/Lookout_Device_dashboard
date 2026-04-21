"""
Device Service Module

Handles all device-related business logic including:
- Fetching devices from API
- Device data processing 
- Cache management coordination
- Delta sync operations
"""

import json
import logging
import time
from datetime import datetime
from typing import List, Dict, Optional, Any

from lookout_client import LookoutMRAClient, LookoutAPIError
from device_cache import DeviceCache, enhanced_device_mapping
from services.tenant_service import TenantService, Tenant
from utils.time_utils import days_since_checkin_from_device, get_connection_status

logger = logging.getLogger(__name__)


class DeviceService:
    """Service class for managing device operations"""
    
    def __init__(self, config_class, device_cache: DeviceCache, tenant_service: Optional['TenantService'] = None):
        """
        Initialize device service
        
        Args:
            config_class: Configuration class instance
            device_cache: Device cache instance
            tenant_service: Optional tenant service for multi-tenant support
        """
        self.config = config_class
        self.device_cache = device_cache
        self.lookout_client = None
        self.tenant_service = tenant_service
        self.tenant_clients: Dict[str, LookoutMRAClient] = {}
    
    def get_lookout_client(self) -> Optional[LookoutMRAClient]:
        """Get or create Lookout API client"""
        if self.lookout_client is None:
            try:
                self.lookout_client = LookoutMRAClient(config=self.config)
                logger.info("Lookout API client initialized")
            except LookoutAPIError as e:
                logger.error(f"Failed to initialize Lookout API client: {e}")
                self.lookout_client = None
        return self.lookout_client
    
    def fetch_and_cache_devices(self) -> List[Dict]:
        """
        Fetch devices from API and update cache
        Supports both single-tenant and multi-tenant modes
        
        Returns:
            List of device dictionaries
            
        Raises:
            Exception: If unable to fetch devices from any source
        """
        start_time = datetime.now()
        
        # Check if we should use sample data (development mode)
        use_sample_data = self.config.USE_SAMPLE_DATA
        
        if use_sample_data:
            devices = self._load_sample_data()
        elif self.config.ENABLE_MULTI_TENANT and self.tenant_service:
            devices = self._fetch_from_all_tenants()
        else:
            devices = self._fetch_from_api()
        
        # Calculate API response time
        api_response_time = (datetime.now() - start_time).total_seconds()
        
        # Update cache
        self.device_cache.update_devices(devices, api_response_time)
        
        return devices
    
    def _load_sample_data(self) -> List[Dict]:
        """Load sample data from file"""
        try:
            with open('sample_data.json', 'r') as f:
                raw_devices = json.load(f)
            logger.info("Using sample data for development")
            # Sample data is already mapped, so use as-is
            return raw_devices
        except FileNotFoundError:
            logger.error("Sample data file not found")
            raise Exception("Sample data file not found")
    
    def _fetch_from_all_tenants(self) -> List[Dict]:
        """
        Fetch devices from all enabled tenants and tag with MDM identifier
        
        Returns:
            List of devices from all tenants with mdm_identifier field
        """
        if not self.tenant_service:
            logger.warning("Tenant service not available for multi-tenant fetch")
            return []
            
        all_devices = []
        tenants = self.tenant_service.get_all_tenants(enabled_only=True)
        
        logger.info(f"Fetching devices from {len(tenants)} tenants")
        
        for tenant in tenants:
            try:
                logger.info(f"Fetching devices for tenant: {tenant.tenant_name} (MDM: {tenant.mdm_identifier})")
                
                # Get or create client for this tenant
                client = self._get_tenant_client(tenant)
                
                # Fetch devices for this tenant
                raw_devices = self._fetch_all_devices_efficiently(client)
                
                # Map and tag devices with MDM identifier
                tenant_devices = []
                for device in raw_devices:
                    mapped_device = enhanced_device_mapping(device)
                    # Add tenant and MDM metadata
                    mapped_device['mdm_identifier'] = tenant.mdm_identifier
                    mapped_device['mdm_provider'] = tenant.mdm_provider
                    mapped_device['tenant_id'] = tenant.tenant_id
                    mapped_device['tenant_name'] = tenant.tenant_name
                    tenant_devices.append(mapped_device)
                
                all_devices.extend(tenant_devices)
                logger.info(f"Retrieved {len(tenant_devices)} devices from {tenant.tenant_name}")
                
            except Exception as e:
                logger.error(f"Failed to fetch devices from tenant {tenant.tenant_name}: {e}")
                # Continue with other tenants even if one fails
                continue
        
        logger.info(f"Total devices fetched from all tenants: {len(all_devices)}")
        return all_devices
    
    def _get_tenant_client(self, tenant: Tenant) -> LookoutMRAClient:
        """
        Get or create Lookout API client for specific tenant
        
        Args:
            tenant: Tenant configuration
            
        Returns:
            Authenticated Lookout API client
        """
        tenant_id = tenant.tenant_id
        
        # Check if client already exists
        if tenant_id in self.tenant_clients:
            client = self.tenant_clients[tenant_id]
            if client.is_authenticated():
                return client
        
        # Create new client
        logger.info(f"Creating new API client for tenant: {tenant.tenant_name}")
        client = LookoutMRAClient(application_key=tenant.lookout_application_key, config=self.config)
        client.authenticate()
        
        # Cache the client
        self.tenant_clients[tenant_id] = client
        
        return client
    
    def _fetch_from_api(self) -> List[Dict]:
        """Fetch devices from production API (single tenant mode)"""
        devices = []
        try:
            client = self.get_lookout_client()
            if client is None:
                raise Exception("API client not available")
            
            # Ensure authentication
            if not client.is_authenticated():
                client.authenticate()
            
            # Fetch devices from Lookout API with pagination
            logger.info("Fetching devices from Lookout API")
            raw_devices = self._fetch_all_devices_efficiently(client)
            
            # Map devices to dashboard format using enhanced mapping
            devices = [enhanced_device_mapping(device) for device in raw_devices]
            logger.info(f"Successfully fetched and mapped {len(devices)} devices from Lookout API", extra={'devices_count': len(devices)})
            
            return devices
            
        except LookoutAPIError as e:
            logger.error(f"Lookout API error during device fetch: {str(e)}", extra={'error_type': 'api_error'})
            # Fallback to sample data on API error
            return self._load_sample_data_fallback()
        except Exception as e:
            logger.error(f"Unexpected error during device fetch: {str(e)}", extra={'error_type': 'unexpected'})
            raise
    
    def _load_sample_data_fallback(self) -> List[Dict]:
        """Load sample data as fallback when API fails"""
        try:
            with open('sample_data.json', 'r') as f:
                raw_devices = json.load(f)
            logger.info("Fallback to sample data due to API error")
            return raw_devices
        except FileNotFoundError:
            logger.error("Sample data file not found")
            raise Exception("API unavailable and no sample data found")
    
    def _fetch_all_devices_efficiently(self, client: LookoutMRAClient) -> List[Dict]:
        """
        Use pagination to handle large device lists with retry logic
        
        Args:
            client: Authenticated Lookout API client
            
        Returns:
            List of raw device data from API
        """
        all_devices = []
        oid = None  # Start from beginning
        max_retries = 3
        base_delay = 1  # seconds
        
        while True:
            params = {'limit': 1000}
            if oid:
                params['oid'] = oid
            
            for attempt in range(max_retries):
                try:
                    response = client.get_devices(**params)
                    devices = response.get('devices', []) if isinstance(response, dict) else response
                    
                    if not devices:
                        return all_devices
                        
                    all_devices.extend(devices)
                    
                    # Get last oid for next page
                    if len(devices) < 1000:  # Last page
                        return all_devices
                    oid = devices[-1].get('oid')
                    
                    if not oid:  # No oid field, can't paginate
                        return all_devices
                    
                    break  # Success, exit retry loop
                
                except LookoutAPIError as e:
                    if 'rate limit' in str(e).lower() and attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(f"Rate limit hit, retrying in {delay} seconds (attempt {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                    else:
                        logger.error(f"API error after {max_retries} attempts: {e}")
                        raise
                except Exception as e:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"Unexpected error, retrying in {delay} seconds (attempt {attempt + 1}/{max_retries}): {e}")
                        time.sleep(delay)
                    else:
                        logger.error(f"Unexpected error after {max_retries} attempts: {e}")
                        raise
        
        return all_devices
    
    def fetch_device_deltas(self) -> List[Dict]:
        """
        Fetch only devices updated since last sync
        
        Returns:
            List of updated device dictionaries
        """
        # Get last update time from cache
        cache_stats = self.device_cache.get_stats()
        last_sync = cache_stats.get('last_sync_time')
        
        if not last_sync:
            # No previous sync, fetch all devices
            return self.fetch_and_cache_devices()
        
        # For this implementation, we'll fetch all devices and filter client-side
        # In production, you'd use API filters if available
        logger.info("Delta sync: fetching all devices for client-side filtering")
        
        if self.config.USE_SAMPLE_DATA:
            # Sample data doesn't change, so return empty list
            return []
        else:
            client = self.get_lookout_client()
            if client is None:
                raise Exception("API client not available")
            
            if not client.is_authenticated():
                client.authenticate()
            
            # Fetch recent devices (this is simplified - in production you'd use API filters)
            raw_devices = client.get_devices(limit=1000)
            devices = [enhanced_device_mapping(device) for device in raw_devices]
            
            # Filter for devices updated since last sync (simplified)
            # In production, you'd parse updated_time fields and compare
            return devices
    
    def get_cached_devices(self, max_age_minutes: int = 60) -> Optional[List[Dict]]:
        """
        Get devices from cache if valid
        
        Args:
            max_age_minutes: Maximum cache age in minutes
            
        Returns:
            List of cached devices or None if cache invalid
        """
        if self.device_cache.is_valid(max_age_minutes):
            logger.info("Serving devices from cache")
            return self.device_cache.get_all_devices()
        return None
    
    def get_device_by_id(self, device_id: str) -> Optional[Dict]:
        """
        Get a specific device by ID

        Args:
            device_id: Device identifier

        Returns:
            Device dictionary or None if not found
        """
        try:
            device = self.device_cache.get_device(device_id)
            if device:
                # Add calculated fields for detailed view
                try:
                    device['days_since_checkin'] = self._calculate_days_since_checkin(device)
                    device['connection_status_info'] = self._get_connection_status_info(device['days_since_checkin'])
                except Exception as e:
                    logger.warning(f"Error calculating device details fields: {e}")
                    device['days_since_checkin'] = -1
                    device['connection_status_info'] = {'status': 'unknown', 'label': 'Unknown', 'color': '#6c757d', 'severity': 'secondary', 'icon': 'question-circle'}
            return device
        except Exception as e:
            logger.error(f"Error retrieving device {device_id}: {e}")
            return None

    def _calculate_days_since_checkin(self, device: Dict) -> int:
        """Calculate days since last checkin for a device"""
        return days_since_checkin_from_device(device)

    def _get_connection_status_info(self, days_since: int) -> Dict[str, str]:
        """Get connection status information"""
        return get_connection_status(days_since)
    
    def refresh_devices(self, refresh_type: str = 'full') -> Dict[str, Any]:
        """
        Refresh device data
        
        Args:
            refresh_type: 'full' or 'delta'
            
        Returns:
            Refresh result dictionary
        """
        if refresh_type == 'full':
            # Full refresh - clear cache and fetch all devices
            logger.info("Performing full device refresh")
            self.device_cache.clear()
            devices = self.fetch_and_cache_devices()
            
            return {
                'status': 'success',
                'message': 'Full refresh completed',
                'devices_updated': len(devices),
                'refresh_type': 'full'
            }
            
        elif refresh_type == 'delta':
            # Delta refresh - fetch only updated devices
            logger.info("Performing delta device refresh")
            try:
                updated_devices = self.fetch_device_deltas()
                updates_count = self.device_cache.merge_updates(updated_devices)
                
                return {
                    'status': 'success',
                    'message': 'Delta refresh completed',
                    'devices_updated': updates_count,
                    'refresh_type': 'delta'
                }
            except Exception as e:
                logger.error(f"Delta refresh failed: {e}")
                # Fallback to full refresh
                self.device_cache.clear()
                devices = self.fetch_and_cache_devices()
                
                return {
                    'status': 'success',
                    'message': 'Delta refresh failed, performed full refresh instead',
                    'devices_updated': len(devices),
                    'refresh_type': 'full_fallback'
                }
        else:
            raise ValueError("Invalid refresh type")
    
    def clear_cache(self) -> Dict[str, str]:
        """
        Clear the device cache
        
        Returns:
            Operation result
        """
        self.device_cache.clear()
        logger.info("Cache cleared manually")
        return {
            'status': 'success',
            'message': 'Cache cleared successfully'
        }
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        return self.device_cache.get_stats()

    def get_devices_by_vulnerability(self, cve_name: str) -> List[Dict]:
        """
        Get devices affected by a specific vulnerability (CVE)

        Args:
            cve_name: CVE identifier (e.g., "CVE-2022-36934")

        Returns:
            List of devices affected by the vulnerability
        """
        try:
            client = self.get_lookout_client()
            if client is None:
                logger.warning("API client not available, returning empty list")
                return []

            if not client.is_authenticated():
                client.authenticate()

            # Use the Lookout API to get devices vulnerable to this CVE
            response = client.get_devices_by_cve(cve_name)
            devices = response.get('devices', [])

            # Map devices to dashboard format
            mapped_devices = [enhanced_device_mapping(device) for device in devices]

            logger.info(f"Found {len(mapped_devices)} devices affected by {cve_name}")
            return mapped_devices

        except LookoutAPIError as e:
            logger.error(f"API error fetching devices for CVE {cve_name}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching devices for CVE {cve_name}: {e}")
            return []