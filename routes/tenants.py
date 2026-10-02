"""
Tenant and MDM routes.
"""

import logging
from flask import Blueprint, jsonify, request, g, current_app

from auth import require_auth
from services.risk_service import RiskService
from utils.device_filters import apply_device_filters

logger = logging.getLogger(__name__)
bp = Blueprint('tenants', __name__)


@bp.route('/tenants')
@require_auth
def get_tenants():
    """Get list of all tenants (multi-tenant mode only)"""
    try:
        config_class = current_app.extensions['config_class']
        tenant_service = current_app.extensions.get('tenant_service')
        
        if not config_class.ENABLE_MULTI_TENANT or not tenant_service:
            return jsonify({'error': {'code': 'MULTI_TENANT_DISABLED', 'message': 'Multi-tenant mode not enabled'}}), 400
        
        summary = tenant_service.get_tenants_summary()

        device_cache = current_app.extensions['device_cache']
        sync_status_by_id = {s['tenant_id']: s for s in device_cache.get_tenant_sync_status()}
        for tenant in summary['tenants']:
            status = sync_status_by_id.get(tenant['tenant_id'])
            if not tenant['enabled']:
                tenant['status'] = 'disabled'
                tenant['last_success'] = None
                tenant['last_error'] = None
                tenant['error_message'] = None
                tenant['device_count'] = 0
            elif status:
                tenant['status'] = status['status']
                tenant['last_success'] = status['last_success']
                tenant['last_error'] = status['last_error']
                tenant['error_message'] = status['error_message']
                tenant['device_count'] = status['device_count']
            else:
                tenant['status'] = 'unknown'
                tenant['last_success'] = None
                tenant['last_error'] = None
                tenant['error_message'] = None
                tenant['device_count'] = 0

        return jsonify(summary)
    except Exception as e:
        logger.error(f"Failed to get tenants: {e}", exc_info=True)
        return jsonify({'error': {'code': 'TENANT_FETCH_FAILED', 'message': 'Failed to fetch tenants'}}), 500


@bp.route('/tenants', methods=['POST'])
@require_auth
def create_tenant():
    """Add a new tenant (multi-tenant mode only)"""
    try:
        config_class = current_app.extensions['config_class']
        tenant_service = current_app.extensions.get('tenant_service')

        if not config_class.ENABLE_MULTI_TENANT or not tenant_service:
            return jsonify({'error': {'code': 'MULTI_TENANT_DISABLED', 'message': 'Multi-tenant mode not enabled'}}), 400

        data = request.get_json(silent=True) or {}

        required_fields = ['tenant_id', 'tenant_name', 'mdm_provider', 'mdm_identifier', 'lookout_application_key']
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            return jsonify({'error': {'code': 'VALIDATION_ERROR', 'message': f"Missing or empty field(s): {', '.join(missing_fields)}"}}), 400

        try:
            tenant = tenant_service.add_tenant(
                tenant_id=data['tenant_id'],
                tenant_name=data['tenant_name'],
                mdm_provider=data['mdm_provider'],
                mdm_identifier=data['mdm_identifier'],
                lookout_application_key=data['lookout_application_key'],
                description=data.get('description', ''),
                enabled=data.get('enabled', True)
            )
        except ValueError as e:
            return jsonify({'error': {'code': 'TENANT_CONFLICT', 'message': str(e)}}), 409

        return jsonify(tenant.to_dict()), 201
    except Exception as e:
        logger.error(f"Failed to create tenant: {e}", exc_info=True)
        return jsonify({'error': {'code': 'TENANT_CREATE_FAILED', 'message': 'Failed to create tenant'}}), 500


@bp.route('/tenants/<tenant_id>', methods=['PUT'])
@require_auth
def update_tenant(tenant_id):
    """Update an existing tenant (multi-tenant mode only)"""
    try:
        config_class = current_app.extensions['config_class']
        tenant_service = current_app.extensions.get('tenant_service')

        if not config_class.ENABLE_MULTI_TENANT or not tenant_service:
            return jsonify({'error': {'code': 'MULTI_TENANT_DISABLED', 'message': 'Multi-tenant mode not enabled'}}), 400

        data = request.get_json(silent=True) or {}

        allowed_fields = ['tenant_name', 'mdm_provider', 'mdm_identifier', 'lookout_application_key', 'description']
        fields = {field: data[field] for field in allowed_fields if field in data}

        try:
            tenant = tenant_service.update_tenant(tenant_id, **fields)
        except ValueError as e:
            return jsonify({'error': {'code': 'VALIDATION_ERROR', 'message': str(e)}}), 400

        if tenant is None:
            return jsonify({'error': {'code': 'TENANT_NOT_FOUND', 'message': f"Tenant '{tenant_id}' not found"}}), 404

        return jsonify(tenant.to_dict())
    except Exception as e:
        logger.error(f"Failed to update tenant: {e}", exc_info=True)
        return jsonify({'error': {'code': 'TENANT_UPDATE_FAILED', 'message': 'Failed to update tenant'}}), 500


@bp.route('/tenants/<tenant_id>/suspend', methods=['POST'])
@require_auth
def suspend_tenant(tenant_id):
    """Suspend (disable) a tenant (multi-tenant mode only)"""
    try:
        config_class = current_app.extensions['config_class']
        tenant_service = current_app.extensions.get('tenant_service')

        if not config_class.ENABLE_MULTI_TENANT or not tenant_service:
            return jsonify({'error': {'code': 'MULTI_TENANT_DISABLED', 'message': 'Multi-tenant mode not enabled'}}), 400

        tenant = tenant_service.set_tenant_enabled(tenant_id, False)
        if tenant is None:
            return jsonify({'error': {'code': 'TENANT_NOT_FOUND', 'message': f"Tenant '{tenant_id}' not found"}}), 404

        return jsonify(tenant.to_dict())
    except Exception as e:
        logger.error(f"Failed to suspend tenant: {e}", exc_info=True)
        return jsonify({'error': {'code': 'TENANT_SUSPEND_FAILED', 'message': 'Failed to suspend tenant'}}), 500


@bp.route('/tenants/<tenant_id>/activate', methods=['POST'])
@require_auth
def activate_tenant(tenant_id):
    """Activate (enable) a tenant (multi-tenant mode only)"""
    try:
        config_class = current_app.extensions['config_class']
        tenant_service = current_app.extensions.get('tenant_service')

        if not config_class.ENABLE_MULTI_TENANT or not tenant_service:
            return jsonify({'error': {'code': 'MULTI_TENANT_DISABLED', 'message': 'Multi-tenant mode not enabled'}}), 400

        tenant = tenant_service.set_tenant_enabled(tenant_id, True)
        if tenant is None:
            return jsonify({'error': {'code': 'TENANT_NOT_FOUND', 'message': f"Tenant '{tenant_id}' not found"}}), 404

        return jsonify(tenant.to_dict())
    except Exception as e:
        logger.error(f"Failed to activate tenant: {e}", exc_info=True)
        return jsonify({'error': {'code': 'TENANT_ACTIVATE_FAILED', 'message': 'Failed to activate tenant'}}), 500


@bp.route('/tenants/<tenant_id>/purge', methods=['POST'])
@require_auth
def purge_tenant(tenant_id):
    """Purge a tenant's cached device data (multi-tenant mode only)"""
    try:
        config_class = current_app.extensions['config_class']
        tenant_service = current_app.extensions.get('tenant_service')

        if not config_class.ENABLE_MULTI_TENANT or not tenant_service:
            return jsonify({'error': {'code': 'MULTI_TENANT_DISABLED', 'message': 'Multi-tenant mode not enabled'}}), 400

        if tenant_service.get_tenant_by_id(tenant_id) is None:
            return jsonify({'error': {'code': 'TENANT_NOT_FOUND', 'message': f"Tenant '{tenant_id}' not found"}}), 404

        purged_count = current_app.extensions['device_cache'].purge_tenant_devices(tenant_id)
        current_app.extensions['device_service'].drop_tenant_client(tenant_id)

        return jsonify({'purged_device_count': purged_count, 'tenant_id': tenant_id})
    except Exception as e:
        logger.error(f"Failed to purge tenant devices: {e}", exc_info=True)
        return jsonify({'error': {'code': 'TENANT_PURGE_FAILED', 'message': 'Failed to purge tenant devices'}}), 500


@bp.route('/tenants/<tenant_id>', methods=['DELETE'])
@require_auth
def delete_tenant(tenant_id):
    """Delete a tenant and purge its cached device data (multi-tenant mode only)"""
    try:
        config_class = current_app.extensions['config_class']
        tenant_service = current_app.extensions.get('tenant_service')

        if not config_class.ENABLE_MULTI_TENANT or not tenant_service:
            return jsonify({'error': {'code': 'MULTI_TENANT_DISABLED', 'message': 'Multi-tenant mode not enabled'}}), 400

        if tenant_service.get_tenant_by_id(tenant_id) is None:
            return jsonify({'error': {'code': 'TENANT_NOT_FOUND', 'message': f"Tenant '{tenant_id}' not found"}}), 404

        purged_count = current_app.extensions['device_cache'].purge_tenant_devices(tenant_id)
        current_app.extensions['device_service'].drop_tenant_client(tenant_id)
        tenant_service.delete_tenant(tenant_id)

        return jsonify({'deleted_tenant_id': tenant_id, 'purged_device_count': purged_count})
    except Exception as e:
        logger.error(f"Failed to delete tenant: {e}", exc_info=True)
        return jsonify({'error': {'code': 'TENANT_DELETE_FAILED', 'message': 'Failed to delete tenant'}}), 500


@bp.route('/tenants/<tenant_id>/devices')
@require_auth
def get_tenant_devices(tenant_id):
    """Get devices for a specific tenant"""
    try:
        device_service = current_app.extensions['device_service']
        config_class = current_app.extensions['config_class']
        
        cache_max_age = config_class.CACHE_MAX_AGE_MINUTES
        devices = device_service.get_or_refresh_devices(cache_max_age)

        tenant_devices = [d for d in devices if d.get('tenant_id') == tenant_id]
        
        filtered_devices = apply_device_filters(tenant_devices, request.args, RiskService.analyze_device_risk)
        
        return jsonify({
            'devices': filtered_devices,
            'total_count': len(filtered_devices),
            'tenant_id': tenant_id
        })
        
    except Exception as e:
        logger.error(f"Failed to get tenant devices: {e}", exc_info=True)
        return jsonify({'error': {'code': 'TENANT_DEVICES_FAILED', 'message': str(e)}}), 500


@bp.route('/mdm/<mdm_identifier>/devices')
@require_auth
def get_mdm_devices(mdm_identifier):
    """Get devices by MDM identifier"""
    try:
        device_service = current_app.extensions['device_service']
        config_class = current_app.extensions['config_class']
        
        cache_max_age = config_class.CACHE_MAX_AGE_MINUTES
        devices = device_service.get_or_refresh_devices(cache_max_age)

        mdm_devices = [d for d in devices if d.get('mdm_identifier') == mdm_identifier]
        
        filtered_devices = apply_device_filters(mdm_devices, request.args, RiskService.analyze_device_risk)
        
        return jsonify({
            'devices': filtered_devices,
            'total_count': len(filtered_devices),
            'mdm_identifier': mdm_identifier
        })
        
    except Exception as e:
        logger.error(f"Failed to get MDM devices: {e}", exc_info=True)
        return jsonify({'error': {'code': 'MDM_DEVICES_FAILED', 'message': str(e)}}), 500
