"""
Export routes.
"""

import logging
import os
from datetime import datetime
from flask import Blueprint, jsonify, request, send_file, after_this_request, g, current_app
from flask_limiter import Limiter

from auth import AuthManager, require_auth
from services.export import ExportService
from utils.device_filters import filter_devices_for_export

logger = logging.getLogger(__name__)
bp = Blueprint('export', __name__)
limiter = None


def init_auth(manager: AuthManager, lim: Limiter):
    """Initialize auth manager and limiter"""
    global limiter
    limiter = lim


@bp.route('/export/<format_type>')
@require_auth
def export_data(format_type):
    """Export device data in specified format"""
    try:
        device_service = current_app.extensions['device_service']
        export_service = current_app.extensions['export_service']
        config_class = current_app.extensions['config_class']
        
        cache_max_age = config_class.CACHE_MAX_AGE_MINUTES
        devices = device_service.get_cached_devices(cache_max_age)
        
        if devices is None:
            devices = device_service.fetch_and_cache_devices()
        
        if format_type == 'excel':
            filepath = export_service.export_devices_to_excel(request.args, devices)

            @after_this_request
            def _cleanup(response):
                try:
                    os.remove(filepath)
                except OSError:
                    pass
                return response

            return send_file(filepath, as_attachment=True, download_name=f"device_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        elif format_type == 'csv':
            filtered_devices = filter_devices_for_export(devices, request.args)
            csv_content = export_service.create_csv_export(filtered_devices)
            return csv_content, 200, {'Content-Type': 'text/csv', 'Content-Disposition': f'attachment; filename=device_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'}
        else:
            return jsonify({'error': {'code': 'INVALID_FORMAT', 'message': f'Unsupported format: {format_type}'}}), 400
            
    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        return jsonify({'error': {'code': 'EXPORT_FAILED', 'message': str(e)}}), 500


@bp.route('/export/excel')
@require_auth
def export_excel():
    """Legacy Excel export endpoint"""
    return export_data('excel')
