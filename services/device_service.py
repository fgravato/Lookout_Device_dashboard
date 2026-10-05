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
import os
import threading
import time
from datetime import datetime
from typing import List, Dict, Optional, Any

from lookout_client import LookoutMRAClient, LookoutAPIError
from device_cache import DeviceCache
from services.tenant_service import TenantService, Tenant
from utils.time_utils import days_since_checkin, days_since_checkin_from_device, get_connection_status

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
        self._fetch_condition = threading.Condition()
        self._fetch_in_progress = False
        self._last_fetch_result: List[Dict] = []
        self._last_fetch_error: Optional[Exception] = None
    
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
    
    def get_cve_client(self) -> Optional[LookoutMRAClient]:
        """
        Get an authenticated Lookout API client for CVE/vulnerability queries.

        CVE data is fleet-wide rather than tenant-scoped, so in multi-tenant
        mode this uses the first enabled tenant's client rather than the
        (unset) global client.
        """
        if self.config.ENABLE_MULTI_TENANT and self.tenant_service:
            tenants = self.tenant_service.get_all_tenants(enabled_only=True)
            if not tenants:
                logger.error("No enabled tenants available for CVE client")
                return None
            try:
                return self._get_tenant_client(tenants[0])
            except LookoutAPIError as e:
                logger.error(f"Failed to create CVE client for tenant {tenants[0].tenant_id}: {e}")
                return None
        return self.get_lookout_client()

    def fetch_and_cache_devices(self) -> List[Dict]:
        """
        Fetch devices from API and update cache
        Supports both single-tenant and multi-tenant modes

        A fetch already in progress on another thread is not duplicated -
        callers that arrive while one is running wait for it and reuse its
        result. Without this, e.g. clicking Full Refresh and then immediately
        starting a CVE scan can fire two concurrent fetches against the same
        tenant credentials and trip the Lookout API's rate limit.

        Returns:
            List of device dictionaries

        Raises:
            Exception: If unable to fetch devices from any source
        """
        with self._fetch_condition:
            if self._fetch_in_progress:
                self._fetch_condition.wait()
                if self._last_fetch_error is not None:
                    raise self._last_fetch_error
                return self._last_fetch_result
            self._fetch_in_progress = True

        devices = None
        error = None
        try:
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
        except Exception as e:
            error = e
            raise
        finally:
            with self._fetch_condition:
                self._last_fetch_error = error
                if devices is not None:
                    self._last_fetch_result = devices
                self._fetch_in_progress = False
                self._fetch_condition.notify_all()
    
    def _load_sample_data(self) -> List[Dict]:
        """Load sample data from file"""
        sample_data_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sample_data.json')
        try:
            with open(sample_data_path, 'r') as f:
                raw_devices = json.load(f)
            logger.info("Using sample data for development")
            # Sample data is already mapped, but lacks a device_id/guid; the
            # cache requires one of these to key and store a device, so
            # backfill from the (unique) device_name.
            for device in raw_devices:
                if not device.get('device_id') and not device.get('guid'):
                    device['device_id'] = device.get('device_name')
            return raw_devices
        except FileNotFoundError:
            logger.error(f"Sample data file not found at {sample_data_path}")
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
                self.device_cache.record_tenant_sync_success(tenant.tenant_id, tenant.tenant_name, len(tenant_devices))

            except Exception as e:
                logger.error(f"Failed to fetch devices from tenant {tenant.tenant_name}: {e}")
                self.device_cache.record_tenant_sync_failure(tenant.tenant_id, tenant.tenant_name, str(e))
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
    
    def drop_tenant_client(self, tenant_id: str) -> None:
        """
        Remove a cached API client for a tenant, e.g. after the tenant is
        deleted or purged, so a stale client isn't reused if the tenant_id
        is ever re-added later.

        Args:
            tenant_id: The tenant identifier
        """
        self.tenant_clients.pop(tenant_id, None)

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
        sample_data_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sample_data.json')
        try:
            with open(sample_data_path, 'r') as f:
                raw_devices = json.load(f)
            for device in raw_devices:
                if not device.get('device_id') and not device.get('guid'):
                    device['device_id'] = device.get('device_name')
            logger.info("Fallback to sample data due to API error")
            return raw_devices
        except FileNotFoundError:
            logger.error(f"Sample data file not found at {sample_data_path}")
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

    def get_or_refresh_devices(self, max_age_minutes: int = 60, force_refresh: bool = False) -> List[Dict]:
        """
        Get devices from cache if valid, otherwise fetch and cache fresh devices

        Args:
            max_age_minutes: Maximum cache age in minutes
            force_refresh: If True, bypass the cache and fetch fresh devices

        Returns:
            List of device dictionaries
        """
        if not force_refresh:
            devices = self.get_cached_devices(max_age_minutes)
            if devices is not None:
                return devices
        return self.fetch_and_cache_devices()

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


def enhanced_device_mapping(device: Dict, precompute_analysis: bool = True) -> Dict:
    """
    Enhanced device mapping to extract all available API fields properly.

    Pre-computes days_since_checkin and connection_status_info for performance.
    Risk analysis is computed once and cached in the device dict.

    Args:
        device: Raw device data from API
        precompute_analysis: If True, pre-compute risk analysis (default True)

    Returns:
        Mapped device dict with pre-computed fields
    """
    try:
        # Helper functions for status mapping
        def map_security_status(status):
            mapping = {
                'SECURE': 'Secure',
                'THREATS_LOW': 'Low',
                'THREATS_MEDIUM': 'Medium',
                'THREATS_HIGH': 'High',
                'CRITICAL': 'Critical'
            }
            return mapping.get(status, 'Unknown')

        def map_protection_status(status, days_since, activation_status, risk_level):
            """Enhanced compliance determination based on multiple factors"""
            if not status:
                return 'Unknown'

            # Primary factor: Protection status from Lookout API
            protection_mapping = {
                'PROTECTED': 'Connected',
                'DISCONNECTED': 'Disconnected',
                'UNPROTECTED': 'Pending'
            }

            base_compliance = protection_mapping.get(status, 'Unknown')

            # Enhanced compliance logic based on multiple factors
            if status == 'PROTECTED':
                # Fully compliant if low risk, recently active, and properly activated
                if (risk_level in ['low', 'secure'] and
                    days_since <= 7 and
                    activation_status == 'activated'):
                    return 'Fully Compliant'
                elif days_since <= 30:
                    return 'Connected'
                elif risk_level in ['medium', 'high', 'critical']:
                    return 'At-Risk'
                else:
                    return 'Connected'

            elif status == 'DISCONNECTED':
                if days_since > 30:
                    return 'Non-Compliant'
                else:
                    return 'Disconnected'

            elif status == 'UNPROTECTED':
                if activation_status != 'activated':
                    return 'Pending Activation'
                else:
                    return 'Pending'

            return base_compliance

        # Extract nested objects safely
        software = device.get('software', {}) or {}
        hardware = device.get('hardware', {}) or {}
        client = device.get('client', {}) or {}
        details = device.get('details', {}) or {}

        # Pre-compute days since checkin and connection status
        checkin_time = device.get('checkin_time')
        computed_days_since = days_since_checkin(checkin_time)
        computed_connection_status = get_connection_status(computed_days_since)

        # Get values needed for compliance calculation
        risk_level_raw = map_security_status(device.get('security_status')).lower()
        activation_status = device.get('activation_status', 'Unknown').lower()

        mapped_device = {
            # Basic device information
            'device_name': (
                device.get('customer_device_id') or
                f"Device-{device.get('guid', 'Unknown')[:8]}"
            ),
            'device_id': device.get('guid'),
            'user_email': device.get('email', 'N/A'),
            'platform': device.get('platform', 'Unknown').title(),

            # Timing fields
            'checkin_time': checkin_time,
            'last_checkin': checkin_time,  # For backward compatibility
            'activated_at': device.get('activated_at'),
            'updated_time': device.get('updated_time'),

            # PRE-COMPUTED: Days since checkin and connection status (performance optimization)
            'days_since_checkin': computed_days_since,
            'connection_status_info': computed_connection_status,

            # Software data
            'os_version': software.get('os_version', 'Unknown'),
            'security_patch_level': software.get('security_patch_level'),
            'latest_os_version': software.get('latest_os_version'),
            'latest_security_patch_level': software.get('latest_security_patch_level'),
            'sdk_version': software.get('sdk_version'),
            'os_version_date': software.get('os_version_date'),
            'rsr': software.get('rsr'),

            # MDM information from Lookout API
            'mdm_connector_id': details.get('mdm_connector_id'),
            'mdm_connector_uuid': details.get('mdm_connector_uuid'),
            'external_id': details.get('external_id'),

            # Multi-tenant fields (added by device service if in multi-tenant mode)
            'mdm_identifier': device.get('mdm_identifier'),
            'mdm_provider': device.get('mdm_provider'),
            'tenant_id': device.get('tenant_id'),
            'tenant_name': device.get('tenant_name'),

            # Hardware details
            'manufacturer': hardware.get('manufacturer'),
            'model': hardware.get('model'),

            # Client/App information
            'app_version': client.get('package_version'),
            'package_name': client.get('package_name'),
            'lookout_sdk_version': client.get('lookout_sdk_version'),
            'ota_version': client.get('ota_version'),

            # Status mappings
            'risk_level': map_security_status(device.get('security_status')),
            'security_status': device.get('security_status'),
            'compliance_status': map_protection_status(
                device.get('protection_status'),
                computed_days_since,
                activation_status,
                risk_level_raw
            ),
            'protection_status': device.get('protection_status'),
            'activation_status': device.get('activation_status', 'Unknown'),

            # Additional useful fields
            'locale': device.get('locale'),
            'enterprise_guid': device.get('enterprise_guid'),
            'device_group_guid': device.get('device_group_guid'),
            'device_group_name': device.get('device_group_name'),
            'mdm_type': device.get('mdm_type'),
            'mdm_id': device.get('mdm_id'),
            'profile_type': device.get('profile_type'),

            # Enhanced threat information
            'threats': device.get('threats', []),
            'threat_family_names': [threat.get('family_name', '') for threat in device.get('threats', []) if threat.get('family_name')],
            'threat_descriptions': [threat.get('description', '') for threat in device.get('threats', []) if threat.get('description')],

            # Metadata for tracking
            'oid': device.get('oid'),
            'guid': device.get('guid'),
        }

        # Pre-compute risk analysis if requested (avoids recalculating in loops)
        if precompute_analysis:
            try:
                from services.risk_service import RiskService
                mapped_device['risk_analysis'] = RiskService.analyze_device_risk(mapped_device)
            except Exception as e:
                logger.debug(f"Could not pre-compute risk analysis: {e}")
                # Risk analysis will be computed on-demand

        return mapped_device

    except Exception as e:
        logger.error(f"Error in enhanced device mapping: {e}")
        # Return basic mapping as fallback
        return {
            'device_name': device.get('guid', 'Unknown Device'),
            'device_id': device.get('guid', ''),
            'user_email': device.get('email', 'N/A'),
            'platform': device.get('platform', 'Unknown'),
            'risk_level': 'Unknown',
            'checkin_time': device.get('checkin_time'),
            'last_checkin': device.get('checkin_time'),
            'os_version': 'Unknown',
            'app_version': 'Unknown',
            'compliance_status': 'Unknown',
            'days_since_checkin': -1,
            'connection_status_info': get_connection_status(-1)
        }