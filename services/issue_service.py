"""
Issue (Threat) Service

Handles fetching and normalizing Lookout threat data for the Issues tab.
Only calls /mra/api/v2/threats — never /mra/api/v2/pcp-threats — so
Phishing and Content Protection ("web content") alerts never appear here.
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

ALLOWED_FILTERS = (
    'classification', 'risk', 'status', 'threat_type',
    'platform', 'profile_type', 'timeframe', 'device_guid', 'query', 'oid'
)


class IssueService:
    """Service for fetching device threats/issues"""

    def __init__(self, lookout_client, device_cache=None):
        """
        Initialize issue service

        Args:
            lookout_client: Authenticated Lookout API client
            device_cache: Optional DeviceCache for enriching issues with
                device owner/name/platform/model
        """
        self.lookout_client = lookout_client
        self.device_cache = device_cache

    def get_issues(self, limit: int = 100, **filters) -> List[Dict[str, Any]]:
        """
        Get threats/issues from the fleet, enriched with device details

        Args:
            limit: Maximum number of issues to retrieve
            **filters: classification, risk, status, threat_type, platform,
                profile_type, timeframe, device_guid, query, oid

        Returns:
            List of threat dictionaries, each with a 'device_info' key
        """
        try:
            if not self.lookout_client.is_authenticated():
                self.lookout_client.authenticate()

            params = {k: v for k, v in filters.items() if k in ALLOWED_FILTERS and v}
            data = self.lookout_client.get_threats(limit=limit, **params)
            issues = data.get('threats', [])

            for issue in issues:
                issue['device_info'] = self._get_device_info(issue)

            logger.info(f"Retrieved {len(issues)} issues")
            return issues

        except Exception as e:
            logger.error(f"Failed to get issues: {e}")
            return []

    def _get_device_info(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        """Build device owner/name/platform/model info for an issue"""
        nested_device = issue.get('device') or {}
        guid = issue.get('device_guid') or nested_device.get('guid')

        info = {
            'owner_email': nested_device.get('email'),
            'device_name': None,
            'platform': None,
            'model': None,
        }

        if self.device_cache and guid:
            cached = self.device_cache.get_device(guid)
            if cached:
                info['owner_email'] = cached.get('user_email') or info['owner_email']
                info['device_name'] = cached.get('device_name')
                info['platform'] = cached.get('platform')
                info['model'] = cached.get('model')

        return info
