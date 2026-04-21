"""
Device Cache Module for Lookout MRA Desktop Dashboard

Provides in-memory caching with optional persistence for device data.
Pre-computes risk analysis and connection status for performance.
"""

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging

from utils.time_utils import days_since_checkin, get_connection_status

logger = logging.getLogger(__name__)


class DeviceCache:
    """In-memory cache for device data with optional SQLite persistence"""
    
    def __init__(self, enable_persistence: bool = False, cache_file: str = './device_cache.db'):
        self.devices: Dict[str, Dict] = {}  # {device_id: device_data}
        self.last_updated: Optional[datetime] = None
        self.cache_metadata = {
            'total_devices': 0,
            'last_sync_time': None,
            'api_response_time': None,
            'cache_hits': 0,
            'cache_misses': 0
        }
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Optional persistence
        self.enable_persistence = enable_persistence
        self.cache_file = cache_file
        
        if self.enable_persistence:
            self._init_persistence()
            self._load_from_disk()
    
    def _init_persistence(self):
        """Initialize SQLite database for persistence"""
        try:
            with sqlite3.connect(self.cache_file) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS device_cache (
                        device_id TEXT PRIMARY KEY,
                        device_data TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS cache_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                conn.commit()
                logger.info("SQLite persistence initialized")
        except Exception as e:
            logger.error(f"Failed to initialize persistence: {e}")
            self.enable_persistence = False
    
    def _load_from_disk(self):
        """Load cached data from SQLite on startup"""
        if not self.enable_persistence:
            return
            
        try:
            with sqlite3.connect(self.cache_file) as conn:
                # Load devices
                cursor = conn.execute('SELECT device_id, device_data FROM device_cache')
                for device_id, device_data_json in cursor.fetchall():
                    device_data = json.loads(device_data_json)
                    self.devices[device_id] = device_data
                
                # Load metadata
                cursor = conn.execute('SELECT key, value FROM cache_metadata')
                for key, value in cursor.fetchall():
                    if key == 'last_updated':
                        self.last_updated = datetime.fromisoformat(value) if value else None
                    else:
                        self.cache_metadata[key] = json.loads(value) if value else None
                
                logger.info(f"Loaded {len(self.devices)} devices from disk cache")
        except Exception as e:
            logger.error(f"Failed to load from disk: {e}")
    
    def _save_to_disk(self):
        """Save current cache to SQLite using efficient bulk operations"""
        if not self.enable_persistence:
            return
            
        try:
            with sqlite3.connect(self.cache_file) as conn:
                # Use executemany with INSERT OR REPLACE for efficient bulk upsert
                device_data = [
                    (device_id, json.dumps(device_data))
                    for device_id, device_data in self.devices.items()
                ]
                
                conn.executemany(
                    'INSERT OR REPLACE INTO device_cache (device_id, device_data, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)',
                    device_data
                )
                
                # Clear and save metadata (small dataset, DELETE is fine)
                conn.execute('DELETE FROM cache_metadata')
                
                metadata_to_save = [
                    ('last_updated', self.last_updated.isoformat() if self.last_updated else None)
                ]
                
                for key, value in self.cache_metadata.items():
                    metadata_to_save.append((key, json.dumps(value)))
                
                conn.executemany(
                    'INSERT INTO cache_metadata (key, value) VALUES (?, ?)',
                    metadata_to_save
                )
                
                conn.commit()
                logger.debug(f"Cache saved to disk: {len(device_data)} devices")
        except Exception as e:
            logger.error(f"Failed to save to disk: {e}")
    
    def update_devices(self, devices: List[Dict], api_response_time: float = None):
        """Update cache with new device data"""
        with self._lock:
            start_time = datetime.now()
            
            # Clear existing devices
            self.devices.clear()
            
            # Add new devices
            for device in devices:
                device_id = device.get('device_id') or device.get('guid')
                if device_id:
                    self.devices[device_id] = device
            
            # Update metadata
            self.last_updated = start_time
            self.cache_metadata.update({
                'total_devices': len(self.devices),
                'last_sync_time': start_time.isoformat(),
                'api_response_time': api_response_time
            })
            
            # Save to disk if persistence enabled
            self._save_to_disk()
            
            logger.info(f"Cache updated with {len(devices)} devices")
    
    def merge_updates(self, updated_devices: List[Dict]):
        """Merge updated devices into existing cache"""
        with self._lock:
            updates_count = 0
            
            for device in updated_devices:
                device_id = device.get('device_id') or device.get('guid')
                if device_id:
                    self.devices[device_id] = device
                    updates_count += 1
            
            # Update metadata
            self.cache_metadata['total_devices'] = len(self.devices)
            
            # Save to disk if persistence enabled
            if updates_count > 0:
                self._save_to_disk()
            
            logger.info(f"Merged {updates_count} device updates into cache")
            return updates_count
    
    def get_all_devices(self) -> List[Dict]:
        """Get all cached devices"""
        with self._lock:
            self.cache_metadata['cache_hits'] += 1
            return list(self.devices.values())
    
    def get_device(self, device_id: str) -> Optional[Dict]:
        """Get a specific device by ID"""
        with self._lock:
            device = self.devices.get(device_id)
            if device:
                self.cache_metadata['cache_hits'] += 1
            else:
                self.cache_metadata['cache_misses'] += 1
            return device
    
    def get_filtered_devices(self, filters: Dict) -> List[Dict]:
        """Get devices matching filters"""
        with self._lock:
            devices = list(self.devices.values())
            self.cache_metadata['cache_hits'] += 1
            
            # Apply filters (this will be handled by the main app logic)
            return devices
    
    def is_valid(self, max_age_minutes: int = 60) -> bool:
        """Check if cache is valid (not too old)"""
        with self._lock:
            if not self.last_updated:
                return False

            age = datetime.now() - self.last_updated
            return age < timedelta(minutes=max_age_minutes)
    
    def clear(self):
        """Clear all cached data"""
        with self._lock:
            self.devices.clear()
            self.last_updated = None
            self.cache_metadata.update({
                'total_devices': 0,
                'last_sync_time': None
            })
            
            if self.enable_persistence:
                try:
                    with sqlite3.connect(self.cache_file) as conn:
                        conn.execute('DELETE FROM device_cache')
                        conn.execute('DELETE FROM cache_metadata')
                        conn.commit()
                except Exception as e:
                    logger.error(f"Failed to clear disk cache: {e}")
            
            logger.info("Cache cleared")
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        with self._lock:
            stats = self.cache_metadata.copy()
            stats.update({
                'cached_devices': len(self.devices),
                'cache_age_minutes': (
                    (datetime.now() - self.last_updated).total_seconds() / 60
                    if self.last_updated else None
                ),
                'is_valid': self.is_valid(),
                'persistence_enabled': self.enable_persistence
            })
            return stats


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