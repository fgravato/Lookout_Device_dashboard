"""
Issue (Threat) routes.
"""

import logging
from flask import Blueprint, jsonify, request, current_app

from auth import require_auth
from services.issue_service import IssueService, DEFAULT_LIMIT

logger = logging.getLogger(__name__)
bp = Blueprint('issues', __name__)


def get_issue_service():
    """Get or create issue service"""
    issue_service = current_app.extensions.get('issue_service')
    if issue_service is None:
        device_service = current_app.extensions['device_service']
        device_cache = current_app.extensions['device_cache']
        client = device_service.get_lookout_client()
        if client:
            issue_service = IssueService(client, device_cache)
            current_app.extensions['issue_service'] = issue_service
    return issue_service


@bp.route('/issues')
@require_auth
def get_issues():
    """Get a page of threats/issues for the fleet"""
    try:
        issue_service = get_issue_service()
        if not issue_service:
            return jsonify({'error': {'code': 'ISSUE_SERVICE_UNAVAILABLE', 'message': 'Issue service not available'}}), 503

        if request.args.get('refresh') == '1':
            issue_service.invalidate_cache()

        limit = request.args.get('limit', DEFAULT_LIMIT, type=int)
        offset = request.args.get('offset', 0, type=int)
        filters = {
            key: request.args.get(key)
            for key in ('classification', 'risk', 'status', 'threat_type', 'platform', 'profile_type', 'timeframe', 'device_guid', 'query')
            if request.args.get(key)
        }

        result = issue_service.get_issues(limit=limit, offset=offset, **filters)
        return jsonify({
            'issues': result['issues'],
            'count': len(result['issues']),
            'total': result['total'],
            'limit': result['limit'],
            'offset': result['offset'],
            'summary': result['summary'],
        })

    except Exception as e:
        logger.error(f"Failed to get issues: {e}")
        return jsonify({'error': {'code': 'ISSUES_FETCH_ERROR', 'message': 'Failed to fetch issues'}}), 500
