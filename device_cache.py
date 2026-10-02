"""
Device Cache Module for Lookout MRA Desktop Dashboard

Provides in-memory caching with optional persistence for device data.
"""

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging

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
        self.tenant_sync_status: Dict[str, Dict] = {}  # {tenant_id: status_data}
        
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

    def record_tenant_sync_success(self, tenant_id: str, tenant_name: str, device_count: int):
        """Record a successful device sync for a tenant"""
        with self._lock:
            self.tenant_sync_status[tenant_id] = {
                'tenant_id': tenant_id,
                'tenant_name': tenant_name,
                'status': 'ok',
                'last_success': datetime.now().isoformat(),
                'last_error': None,
                'error_message': None,
                'device_count': device_count
            }

    def record_tenant_sync_failure(self, tenant_id: str, tenant_name: str, error_message: str):
        """Record a failed device sync for a tenant, preserving last known good state"""
        with self._lock:
            existing = self.tenant_sync_status.get(tenant_id)
            last_success = existing['last_success'] if existing else None
            device_count = existing['device_count'] if existing else 0

            self.tenant_sync_status[tenant_id] = {
                'tenant_id': tenant_id,
                'tenant_name': tenant_name,
                'status': 'error',
                'last_success': last_success,
                'last_error': datetime.now().isoformat(),
                'error_message': error_message,
                'device_count': device_count
            }

    def get_tenant_sync_status(self) -> List[Dict]:
        """Get sync status for all tenants"""
        with self._lock:
            return list(self.tenant_sync_status.values())

    def purge_tenant_devices(self, tenant_id: str) -> int:
        """Remove all cached devices and sync status for a tenant"""
        with self._lock:
            device_ids_to_remove = [
                device_id for device_id, device in self.devices.items()
                if device.get('tenant_id') == tenant_id
            ]
            for device_id in device_ids_to_remove:
                del self.devices[device_id]

            self.tenant_sync_status.pop(tenant_id, None)

            self.cache_metadata['total_devices'] = len(self.devices)

            if self.enable_persistence:
                self._save_to_disk()

            logger.info(f"Purged {len(device_ids_to_remove)} devices for tenant {tenant_id}")
            return len(device_ids_to_remove)
