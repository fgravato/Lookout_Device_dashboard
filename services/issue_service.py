"""
Issue (Threat) Service

Handles fetching and normalizing Lookout threat data for the Issues tab.
Only calls /mra/api/v2/threats — never /mra/api/v2/pcp-threats — so
Phishing and Content Protection ("web content") alerts never appear here.
"""

import logging
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

ALLOWED_FILTERS = (
    'classification', 'risk', 'status', 'threat_type',
    'platform', 'profile_type', 'timeframe', 'device_guid', 'query', 'oid'
)

# Free-text filters are length-capped so oversized input can't be
# forwarded to the API or bloated in logs.
TEXT_FILTERS = ('query', 'device_guid', 'oid')
MAX_TEXT_FILTER_LEN = 128

DEFAULT_LIMIT = 100
MAX_LIMIT = 500

# Threats change slowly; a short server-side cache keeps the Help Desk
# UI snappy and avoids hammering the Lookout API on every page turn.
CACHE_TTL_SECONDS = 300
MAX_CACHE_ENTRIES = 32


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
        self._cache: "OrderedDict[Tuple, Tuple[float, List[Dict[str, Any]]]]" = OrderedDict()

    def get_issues(self, limit: int = DEFAULT_LIMIT, offset: int = 0,
                   **filters) -> Dict[str, Any]:
        """
        Get a page of fleet threats/issues, enriched with device details

        Args:
            limit: Page size, clamped to 1..MAX_LIMIT
            offset: Zero-based offset into the result set
            **filters: classification, risk, status, threat_type, platform,
                profile_type, timeframe, device_guid, query, oid

        Returns:
            Dict with 'issues' (page), 'total', 'limit', 'offset'
        """
        limit = self._sanitize_limit(limit)
        offset = max(0, self._sanitize_int(offset, 0))
        params = self._sanitize_filters(filters)

        issues = self._get_cached_issues(params)
        if issues is None:
            issues = self._fetch_issues(params)
            self._store_cached_issues(params, issues)

        return {
            'issues': issues[offset:offset + limit],
            'total': len(issues),
            'limit': limit,
            'offset': offset,
            'summary': summarize_issues(issues),
        }

    def invalidate_cache(self) -> None:
        """Drop all cached threat results (e.g. after incident response)"""
        self._cache.clear()

    @staticmethod
    def _sanitize_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _sanitize_limit(self, limit: Any) -> int:
        return min(max(self._sanitize_int(limit, DEFAULT_LIMIT), 1), MAX_LIMIT)

    def _sanitize_filters(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        params = {}
        for key, value in filters.items():
            if key not in ALLOWED_FILTERS or not value:
                continue
            value = str(value)
            if key in TEXT_FILTERS:
                value = value[:MAX_TEXT_FILTER_LEN]
            params[key] = value
        return params

    def _cache_key(self, params: Dict[str, Any]) -> Tuple:
        return tuple(sorted(params.items()))

    def _get_cached_issues(self, params: Dict[str, Any]):
        key = self._cache_key(params)
        entry = self._cache.get(key)
        if entry is None:
            return None
        timestamp, issues = entry
        if time.monotonic() - timestamp > CACHE_TTL_SECONDS:
            del self._cache[key]
            return None
        # Refresh recency for LRU eviction
        self._cache.move_to_end(key)
        return issues

    def _store_cached_issues(self, params: Dict[str, Any], issues: List[Dict[str, Any]]) -> None:
        self._cache[self._cache_key(params)] = (time.monotonic(), issues)
        while len(self._cache) > MAX_CACHE_ENTRIES:
            self._cache.popitem(last=False)

    def _fetch_issues(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        try:
            if not self.lookout_client.is_authenticated():
                self.lookout_client.authenticate()

            # Over-fetch up to the page ceiling so pagination slices
            # from one API call instead of one call per page.
            data = self.lookout_client.get_threats(limit=MAX_LIMIT, **params)
            issues = data.get('threats', [])

            for issue in issues:
                issue['device_info'] = self._get_device_info(issue)
                issue['is_new'] = _is_recent(issue)

            issues = _sort_for_triage(issues)
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


def _issue_timestamp(issue: Dict[str, Any]) -> str:
    return issue.get('created_time') or issue.get('detected_at') or ''


# Triage order: highest severity first, newest first within a severity.
RISK_RANK = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2, 'ADVISORY': 3}


def _risk_rank(issue: Dict[str, Any]) -> int:
    return RISK_RANK.get((issue.get('risk') or '').upper(), 4)


def _sort_for_triage(issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Severity first, newest first within a severity (ISO timestamps sort
    lexicographically); threats without a timestamp sort last"""
    dated = [i for i in issues if _issue_timestamp(i)]
    undated = [i for i in issues if not _issue_timestamp(i)]
    dated.sort(key=_issue_timestamp, reverse=True)
    dated.sort(key=_risk_rank)  # stable: keeps newest-first within a rank
    undated.sort(key=_risk_rank)
    return dated + undated


def _parse_time(value: str):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _is_recent(issue: Dict[str, Any], hours: int = 24) -> bool:
    """True when the threat was detected within the last `hours` hours"""
    parsed = _parse_time(_issue_timestamp(issue))
    if parsed is None:
        return False
    return datetime.now(timezone.utc) - parsed <= timedelta(hours=hours)


def _needs_attention(issue: Dict[str, Any]) -> bool:
    """Open work: anything not explicitly resolved or ignored"""
    return (issue.get('status') or '').upper() not in ('RESOLVED', 'IGNORED')


def summarize_issues(issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    """At-a-glance triage counts over a result set (no extra API calls)"""
    by_risk: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    open_total = 0
    open_high = 0
    new_24h = 0
    unowned = 0

    for issue in issues:
        risk = (issue.get('risk') or 'UNKNOWN').upper()
        status = (issue.get('status') or 'UNKNOWN').upper()
        by_risk[risk] = by_risk.get(risk, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1

        if issue.get('is_new'):
            new_24h += 1
        if not (issue.get('device_info') or {}).get('owner_email'):
            unowned += 1
        if _needs_attention(issue):
            open_total += 1
            if risk == 'HIGH':
                open_high += 1

    return {
        'total': len(issues),
        'open_total': open_total,
        'open_high': open_high,
        'new_24h': new_24h,
        'unowned': unowned,
        'by_risk': by_risk,
        'by_status': by_status,
    }
