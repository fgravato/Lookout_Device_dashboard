"""
Tenant Service Module

Handles multi-tenant configuration and management:
- Loading tenant configurations
- Managing tenant API clients
- Tenant validation and status
"""

import json
import logging
import os
import threading
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Tenant:
    """Represents a single Lookout tenant with MDM configuration"""
    tenant_id: str
    tenant_name: str
    mdm_provider: str
    mdm_identifier: str
    lookout_application_key: str
    description: str = ""
    enabled: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert tenant to dictionary"""
        return {
            'tenant_id': self.tenant_id,
            'tenant_name': self.tenant_name,
            'mdm_provider': self.mdm_provider,
            'mdm_identifier': self.mdm_identifier,
            'description': self.description,
            'enabled': self.enabled
        }


class TenantService:
    """Service class for managing multi-tenant configurations"""
    
    def __init__(self, config_file: str):
        """
        Initialize tenant service
        
        Args:
            config_file: Path to tenants configuration JSON file
        """
        self.config_file = config_file
        self.tenants: List[Tenant] = []
        self._lock = threading.RLock()
        self._load_tenants()

    def _load_tenants(self):
        """Load tenant configurations from JSON file"""
        try:
            with open(self.config_file, 'r') as f:
                config_data = json.load(f)
            
            tenants_data = config_data.get('tenants', [])
            self.tenants = []
            
            for tenant_data in tenants_data:
                tenant = Tenant(
                    tenant_id=tenant_data['tenant_id'],
                    tenant_name=tenant_data['tenant_name'],
                    mdm_provider=tenant_data['mdm_provider'],
                    mdm_identifier=tenant_data['mdm_identifier'],
                    lookout_application_key=tenant_data['lookout_application_key'],
                    description=tenant_data.get('description', ''),
                    enabled=tenant_data.get('enabled', True)
                )
                self.tenants.append(tenant)
            
            logger.info(f"Loaded {len(self.tenants)} tenants from {self.config_file}")
            
        except FileNotFoundError:
            logger.error(f"Tenant configuration file not found: {self.config_file}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in tenant configuration: {e}")
            raise
        except KeyError as e:
            logger.error(f"Missing required field in tenant configuration: {e}")
            raise

    def _save_tenants(self):
        """Persist current tenant list to the config file atomically"""
        config_data = {
            'tenants': [
                {
                    'tenant_id': t.tenant_id,
                    'tenant_name': t.tenant_name,
                    'mdm_provider': t.mdm_provider,
                    'mdm_identifier': t.mdm_identifier,
                    'lookout_application_key': t.lookout_application_key,
                    'description': t.description,
                    'enabled': t.enabled
                }
                for t in self.tenants
            ]
        }

        tmp_path = f"{self.config_file}.tmp"
        with open(tmp_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        os.replace(tmp_path, self.config_file)

        logger.info(f"Saved {len(self.tenants)} tenants to {self.config_file}")

    def add_tenant(self, tenant_id: str, tenant_name: str, mdm_provider: str,
                   mdm_identifier: str, lookout_application_key: str,
                   description: str = '', enabled: bool = True) -> Tenant:
        """
        Add a new tenant

        Args:
            tenant_id: Unique tenant identifier
            tenant_name: Display name for the tenant
            mdm_provider: MDM provider name
            mdm_identifier: MDM identifier
            lookout_application_key: Lookout API application key
            description: Optional description
            enabled: Whether the tenant is enabled

        Returns:
            The newly created Tenant

        Raises:
            ValueError: If a tenant with the given tenant_id or mdm_identifier already exists
        """
        with self._lock:
            if self.get_tenant_by_id(tenant_id) is not None:
                raise ValueError(f"Tenant '{tenant_id}' already exists")
            if self.get_tenant_by_mdm_identifier(mdm_identifier) is not None:
                raise ValueError(f"mdm_identifier '{mdm_identifier}' is already used by another tenant")

            tenant = Tenant(
                tenant_id=tenant_id,
                tenant_name=tenant_name,
                mdm_provider=mdm_provider,
                mdm_identifier=mdm_identifier,
                lookout_application_key=lookout_application_key,
                description=description,
                enabled=enabled
            )
            self.tenants.append(tenant)
            self._save_tenants()
            logger.info(f"Added tenant: {tenant.tenant_name}")
            return tenant

    def update_tenant(self, tenant_id: str, **fields) -> Optional[Tenant]:
        """
        Partially update an existing tenant

        Args:
            tenant_id: The tenant identifier
            **fields: Any of tenant_name, mdm_provider, mdm_identifier,
                lookout_application_key, description

        Returns:
            The updated Tenant, or None if not found

        Raises:
            ValueError: If tenant_name/mdm_provider/mdm_identifier would be
                blanked out, or mdm_identifier would collide with another tenant
        """
        with self._lock:
            tenant = self.get_tenant_by_id(tenant_id)
            if tenant is None:
                return None

            allowed_fields = {'tenant_name', 'mdm_provider', 'mdm_identifier',
                               'lookout_application_key', 'description'}
            required_fields = {'tenant_name', 'mdm_provider', 'mdm_identifier'}

            # Validate all fields up front so a later invalid field can't leave
            # the in-memory Tenant partially mutated by an earlier setattr.
            to_apply = {}
            for field, value in fields.items():
                if field not in allowed_fields:
                    continue
                if field == 'lookout_application_key' and not value:
                    continue
                if field in required_fields and not value:
                    raise ValueError(f"{field} cannot be blank")
                to_apply[field] = value

            if 'mdm_identifier' in to_apply:
                existing = self.get_tenant_by_mdm_identifier(to_apply['mdm_identifier'])
                if existing is not None and existing.tenant_id != tenant_id:
                    raise ValueError(
                        f"mdm_identifier '{to_apply['mdm_identifier']}' is already used by another tenant"
                    )

            for field, value in to_apply.items():
                setattr(tenant, field, value)

            self._save_tenants()
            logger.info(f"Updated tenant: {tenant.tenant_name}")
            return tenant

    def set_tenant_enabled(self, tenant_id: str, enabled: bool) -> Optional[Tenant]:
        """
        Enable or disable a tenant

        Args:
            tenant_id: The tenant identifier
            enabled: New enabled state

        Returns:
            The updated Tenant, or None if not found
        """
        with self._lock:
            tenant = self.get_tenant_by_id(tenant_id)
            if tenant is None:
                return None

            tenant.enabled = enabled
            self._save_tenants()
            logger.info(f"Tenant {tenant.tenant_name} enabled set to {enabled}")
            return tenant

    def delete_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """
        Remove a tenant

        Args:
            tenant_id: The tenant identifier

        Returns:
            The removed Tenant, or None if not found
        """
        with self._lock:
            tenant = self.get_tenant_by_id(tenant_id)
            if tenant is None:
                return None

            self.tenants.remove(tenant)
            self._save_tenants()
            logger.info(f"Deleted tenant: {tenant.tenant_name}")
            return tenant

    def get_all_tenants(self, enabled_only: bool = True) -> List[Tenant]:
        """
        Get all tenants
        
        Args:
            enabled_only: If True, return only enabled tenants
            
        Returns:
            List of tenant objects
        """
        if enabled_only:
            return [t for t in self.tenants if t.enabled]
        return self.tenants
    
    def get_tenant_by_id(self, tenant_id: str) -> Optional[Tenant]:
        """
        Get a specific tenant by ID
        
        Args:
            tenant_id: The tenant identifier
            
        Returns:
            Tenant object or None if not found
        """
        for tenant in self.tenants:
            if tenant.tenant_id == tenant_id:
                return tenant
        return None
    
    def get_tenant_by_mdm_identifier(self, mdm_identifier: str) -> Optional[Tenant]:
        """
        Get a specific tenant by MDM identifier
        
        Args:
            mdm_identifier: The MDM identifier
            
        Returns:
            Tenant object or None if not found
        """
        for tenant in self.tenants:
            if tenant.mdm_identifier == mdm_identifier:
                return tenant
        return None
    
    def get_enabled_tenants_count(self) -> int:
        """Get count of enabled tenants"""
        return len([t for t in self.tenants if t.enabled])
    
    def get_mdm_identifiers(self) -> List[str]:
        """
        Get list of all MDM identifiers from enabled tenants
        
        Returns:
            List of MDM identifier strings
        """
        return [t.mdm_identifier for t in self.tenants if t.enabled]
    
    def validate_tenants(self) -> List[str]:
        """
        Validate tenant configurations
        
        Returns:
            List of validation error messages (empty if all valid)
        """
        errors = []
        
        if not self.tenants:
            errors.append("No tenants configured")
            return errors
        
        # Check for duplicate tenant IDs
        tenant_ids = [t.tenant_id for t in self.tenants]
        if len(tenant_ids) != len(set(tenant_ids)):
            errors.append("Duplicate tenant_id found in configuration")
        
        # Check for duplicate MDM identifiers
        mdm_ids = [t.mdm_identifier for t in self.tenants]
        if len(mdm_ids) != len(set(mdm_ids)):
            errors.append("Duplicate mdm_identifier found in configuration")
        
        # Validate each tenant
        for tenant in self.tenants:
            if not tenant.tenant_id:
                errors.append("Tenant missing tenant_id")
            if not tenant.mdm_identifier:
                errors.append(f"Tenant {tenant.tenant_id} missing mdm_identifier")
            if not tenant.lookout_application_key:
                errors.append(f"Tenant {tenant.tenant_id} missing lookout_application_key")
        
        return errors
    
    def get_tenants_summary(self) -> Dict[str, Any]:
        """
        Get summary of tenant configuration
        
        Returns:
            Dictionary with tenant statistics
        """
        return {
            'total_tenants': len(self.tenants),
            'enabled_tenants': self.get_enabled_tenants_count(),
            'disabled_tenants': len(self.tenants) - self.get_enabled_tenants_count(),
            'mdm_providers': list(set([t.mdm_provider for t in self.tenants if t.enabled])),
            'tenants': [t.to_dict() for t in self.tenants]
        }
