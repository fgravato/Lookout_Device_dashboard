"""
Tests for the TenantService write path (add/update/enable/delete + persistence).
"""

import json
import tempfile
import os

import pytest

from services.tenant_service import TenantService


def make_config_file(tenants=None):
    """Create a temp JSON config file and return its path"""
    fd, path = tempfile.mkstemp(suffix='.json')
    os.close(fd)
    with open(path, 'w') as f:
        json.dump({'tenants': tenants or []}, f)
    return path


class TestAddTenant:
    """Test suite for TenantService.add_tenant"""

    def test_add_tenant_succeeds_and_persists(self):
        config_file = make_config_file()
        service = TenantService(config_file)

        tenant = service.add_tenant(
            tenant_id='tenant_1',
            tenant_name='Company A',
            mdm_provider='InTune',
            mdm_identifier='intune-1',
            lookout_application_key='secret-key',
            description='Test tenant'
        )

        assert tenant.tenant_id == 'tenant_1'
        assert tenant.enabled is True

        # Reload a fresh service from the same file to confirm persistence
        reloaded = TenantService(config_file)
        reloaded_tenant = reloaded.get_tenant_by_id('tenant_1')
        assert reloaded_tenant is not None
        assert reloaded_tenant.tenant_name == 'Company A'
        assert reloaded_tenant.mdm_provider == 'InTune'
        assert reloaded_tenant.mdm_identifier == 'intune-1'
        assert reloaded_tenant.lookout_application_key == 'secret-key'
        assert reloaded_tenant.description == 'Test tenant'

        os.remove(config_file)

    def test_add_tenant_raises_on_duplicate_id(self):
        config_file = make_config_file()
        service = TenantService(config_file)

        service.add_tenant('tenant_1', 'Company A', 'InTune', 'intune-1', 'secret-key')

        with pytest.raises(ValueError):
            service.add_tenant('tenant_1', 'Company B', 'Workspace ONE', 'ws1-1', 'other-key')

        os.remove(config_file)

    def test_add_tenant_raises_on_duplicate_mdm_identifier(self):
        """Two tenants sharing an mdm_identifier silently break
        get_tenant_by_mdm_identifier/MDM-scoped device routing - must be rejected."""
        config_file = make_config_file()
        service = TenantService(config_file)

        service.add_tenant('tenant_1', 'Company A', 'InTune', 'intune-1', 'secret-key')

        with pytest.raises(ValueError):
            service.add_tenant('tenant_2', 'Company B', 'InTune', 'intune-1', 'other-key')

        os.remove(config_file)


class TestUpdateTenant:
    """Test suite for TenantService.update_tenant"""

    def test_partial_update_only_changes_specified_fields(self):
        config_file = make_config_file()
        service = TenantService(config_file)
        service.add_tenant('tenant_1', 'Company A', 'InTune', 'intune-1', 'secret-key', description='original')

        updated = service.update_tenant('tenant_1', tenant_name='New Name')

        assert updated.tenant_name == 'New Name'
        assert updated.mdm_provider == 'InTune'
        assert updated.mdm_identifier == 'intune-1'
        assert updated.lookout_application_key == 'secret-key'
        assert updated.description == 'original'

        os.remove(config_file)

    def test_empty_string_key_does_not_change_stored_key(self):
        config_file = make_config_file()
        service = TenantService(config_file)
        service.add_tenant('tenant_1', 'Company A', 'InTune', 'intune-1', 'secret-key')

        updated = service.update_tenant('tenant_1', lookout_application_key='')

        assert updated.lookout_application_key == 'secret-key'

        os.remove(config_file)

    def test_returns_none_for_unknown_tenant_id(self):
        config_file = make_config_file()
        service = TenantService(config_file)

        result = service.update_tenant('unknown', tenant_name='Doesnt Matter')

        assert result is None

        os.remove(config_file)

    def test_raises_on_blank_required_field(self):
        config_file = make_config_file()
        service = TenantService(config_file)
        service.add_tenant('tenant_1', 'Company A', 'InTune', 'intune-1', 'secret-key')

        with pytest.raises(ValueError):
            service.update_tenant('tenant_1', mdm_identifier='')

        # Blank rejected before any mutation - original value untouched
        assert service.get_tenant_by_id('tenant_1').mdm_identifier == 'intune-1'

        os.remove(config_file)

    def test_raises_on_mdm_identifier_collision_with_another_tenant(self):
        config_file = make_config_file()
        service = TenantService(config_file)
        service.add_tenant('tenant_1', 'Company A', 'InTune', 'intune-1', 'secret-key')
        service.add_tenant('tenant_2', 'Company B', 'InTune', 'intune-2', 'other-key')

        with pytest.raises(ValueError):
            service.update_tenant('tenant_2', mdm_identifier='intune-1')

        assert service.get_tenant_by_id('tenant_2').mdm_identifier == 'intune-2'

        os.remove(config_file)

    def test_mdm_identifier_can_be_set_to_its_own_current_value(self):
        """Updating a tenant without changing mdm_identifier (or re-sending the
        same value) must not trip the collision check against itself."""
        config_file = make_config_file()
        service = TenantService(config_file)
        service.add_tenant('tenant_1', 'Company A', 'InTune', 'intune-1', 'secret-key')

        updated = service.update_tenant('tenant_1', mdm_identifier='intune-1', tenant_name='Renamed')

        assert updated.mdm_identifier == 'intune-1'
        assert updated.tenant_name == 'Renamed'

        os.remove(config_file)

    def test_invalid_field_leaves_other_valid_fields_unapplied(self):
        """A ValueError from one field must not leave earlier-iterated fields
        partially applied in memory before the exception is raised."""
        config_file = make_config_file()
        service = TenantService(config_file)
        service.add_tenant('tenant_1', 'Company A', 'InTune', 'intune-1', 'secret-key')

        with pytest.raises(ValueError):
            service.update_tenant('tenant_1', tenant_name='Should Not Apply', mdm_identifier='')

        tenant = service.get_tenant_by_id('tenant_1')
        assert tenant.tenant_name == 'Company A'
        assert tenant.mdm_identifier == 'intune-1'

        os.remove(config_file)


class TestSetTenantEnabled:
    """Test suite for TenantService.set_tenant_enabled"""

    def test_toggles_and_persists(self):
        config_file = make_config_file()
        service = TenantService(config_file)
        service.add_tenant('tenant_1', 'Company A', 'InTune', 'intune-1', 'secret-key')

        disabled = service.set_tenant_enabled('tenant_1', False)
        assert disabled.enabled is False

        reloaded = TenantService(config_file)
        assert reloaded.get_tenant_by_id('tenant_1').enabled is False

        enabled = service.set_tenant_enabled('tenant_1', True)
        assert enabled.enabled is True

        os.remove(config_file)

    def test_returns_none_for_unknown_tenant_id(self):
        config_file = make_config_file()
        service = TenantService(config_file)

        result = service.set_tenant_enabled('unknown', True)

        assert result is None

        os.remove(config_file)


class TestDeleteTenant:
    """Test suite for TenantService.delete_tenant"""

    def test_removes_and_persists(self):
        config_file = make_config_file()
        service = TenantService(config_file)
        service.add_tenant('tenant_1', 'Company A', 'InTune', 'intune-1', 'secret-key')

        removed = service.delete_tenant('tenant_1')

        assert removed.tenant_id == 'tenant_1'
        assert service.get_tenant_by_id('tenant_1') is None

        reloaded = TenantService(config_file)
        assert reloaded.get_tenant_by_id('tenant_1') is None

        os.remove(config_file)

    def test_returns_none_for_unknown_tenant_id(self):
        config_file = make_config_file()
        service = TenantService(config_file)

        result = service.delete_tenant('unknown')

        assert result is None

        os.remove(config_file)
