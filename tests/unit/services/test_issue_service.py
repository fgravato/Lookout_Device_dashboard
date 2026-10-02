"""
Tests for the IssueService class.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from services.issue_service import (
    IssueService,
    DEFAULT_LIMIT,
    MAX_LIMIT,
    MAX_TEXT_FILTER_LEN,
)


def _make_service(threats, authenticated=True):
    client = MagicMock()
    client.is_authenticated.return_value = authenticated
    client.get_threats.return_value = {'threats': threats}
    cache = MagicMock()
    cache.get_device.return_value = None
    return IssueService(client, cache), client


def _threat(guid, created_time=None):
    threat = {'device_guid': guid, 'risk': 'HIGH', 'status': 'OPEN'}
    if created_time is not None:
        threat['created_time'] = created_time
    return threat


class TestGetIssuesPagination:
    """Test suite for limit/offset handling"""

    def test_default_page_returns_metadata(self):
        service, _ = _make_service([_threat('g1')])

        result = service.get_issues()

        assert result['total'] == 1
        assert result['limit'] == DEFAULT_LIMIT
        assert result['offset'] == 0
        assert len(result['issues']) == 1

    def test_limit_is_clamped_to_max(self):
        service, client = _make_service([_threat('g1')])

        result = service.get_issues(limit=9999)

        assert result['limit'] == MAX_LIMIT

    def test_invalid_limit_falls_back_to_default(self):
        service, _ = _make_service([_threat('g1')])

        assert service.get_issues(limit='junk')['limit'] == DEFAULT_LIMIT
        assert service.get_issues(limit=0)['limit'] == 1

    def test_offset_slices_from_cached_results(self):
        threats = [_threat(f'g{i}') for i in range(5)]
        service, client = _make_service(threats)

        page = service.get_issues(limit=2, offset=2)

        assert page['total'] == 5
        assert [t['device_guid'] for t in page['issues']] == ['g2', 'g3']
        # One API call serves every page
        assert client.get_threats.call_count == 1

    def test_negative_offset_is_treated_as_zero(self):
        service, _ = _make_service([_threat('g1')])

        result = service.get_issues(offset=-5)

        assert result['offset'] == 0
        assert len(result['issues']) == 1


class TestGetIssuesCaching:
    """Test suite for server-side threat caching"""

    def test_repeat_call_with_same_filters_hits_cache(self):
        service, client = _make_service([_threat('g1')])

        service.get_issues(risk='HIGH')
        service.get_issues(risk='HIGH')

        assert client.get_threats.call_count == 1

    def test_different_filters_miss_cache(self):
        service, client = _make_service([_threat('g1')])

        service.get_issues(risk='HIGH')
        service.get_issues(risk='LOW')

        assert client.get_threats.call_count == 2

    def test_invalidate_cache_forces_refetch(self):
        service, client = _make_service([_threat('g1')])

        service.get_issues()
        service.invalidate_cache()
        service.get_issues()

        assert client.get_threats.call_count == 2


class TestGetIssuesSanitization:
    """Test suite for filter validation"""

    def test_unknown_filters_are_dropped(self):
        service, client = _make_service([_threat('g1')])

        service.get_issues(risk='HIGH', bogus='x', __class__='y')

        _, kwargs = client.get_threats.call_args
        assert 'bogus' not in kwargs
        assert '__class__' not in kwargs
        assert kwargs['risk'] == 'HIGH'

    def test_text_filters_are_length_capped(self):
        service, client = _make_service([_threat('g1')])

        service.get_issues(query='q' * (MAX_TEXT_FILTER_LEN + 50))

        _, kwargs = client.get_threats.call_args
        assert len(kwargs['query']) == MAX_TEXT_FILTER_LEN

    def test_empty_filters_are_dropped(self):
        service, client = _make_service([_threat('g1')])

        service.get_issues(risk='', status=None)

        _, kwargs = client.get_threats.call_args
        assert 'risk' not in kwargs
        assert 'status' not in kwargs


class TestGetIssuesOrdering:
    """Test suite for triage ordering (severity first, newest first)"""

    def test_highest_severity_comes_first(self):
        threats = [
            {'device_guid': 'low', 'risk': 'LOW', 'created_time': '2024-06-01T00:00:00Z'},
            {'device_guid': 'high', 'risk': 'HIGH', 'created_time': '2024-01-01T00:00:00Z'},
            {'device_guid': 'med', 'risk': 'MEDIUM', 'created_time': '2024-06-01T00:00:00Z'},
        ]
        service, _ = _make_service(threats)

        guids = [t['device_guid'] for t in service.get_issues()['issues']]

        assert guids == ['high', 'med', 'low']

    def test_newest_comes_first_within_a_severity(self):
        threats = [
            _threat('old', '2024-01-01T00:00:00Z'),
            _threat('new', '2024-06-01T00:00:00Z'),
            _threat('mid', '2024-03-01T00:00:00Z'),
        ]
        service, _ = _make_service(threats)

        guids = [t['device_guid'] for t in service.get_issues()['issues']]

        assert guids == ['new', 'mid', 'old']

    def test_threats_without_timestamp_sort_last(self):
        threats = [_threat('nodate'), _threat('dated', '2024-06-01T00:00:00Z')]
        service, _ = _make_service(threats)

        guids = [t['device_guid'] for t in service.get_issues()['issues']]

        assert guids == ['dated', 'nodate']


class TestGetIssuesSummary:
    """Test suite for triage summary counts"""

    def test_summary_counts_open_high_new_and_unowned(self):
        recent = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        threats = [
            {'device_guid': 'g1', 'risk': 'HIGH', 'status': 'OPEN',
             'created_time': recent, 'device': {'email': 'a@example.com'}},
            {'device_guid': 'g2', 'risk': 'HIGH', 'status': 'RESOLVED',
             'created_time': '2020-01-01T00:00:00Z'},
            {'device_guid': 'g3', 'risk': 'LOW', 'status': 'OPEN',
             'created_time': '2020-01-01T00:00:00Z'},
        ]
        service, _ = _make_service(threats)

        summary = service.get_issues()['summary']

        assert summary['total'] == 3
        assert summary['open_total'] == 2
        assert summary['open_high'] == 1
        assert summary['new_24h'] == 1
        assert summary['unowned'] == 2
        assert summary['by_risk'] == {'HIGH': 2, 'LOW': 1}

    def test_recent_threats_are_flagged_new(self):
        recent = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        threats = [
            {'device_guid': 'new', 'created_time': recent},
            {'device_guid': 'old', 'created_time': '2020-01-01T00:00:00Z'},
            {'device_guid': 'nodate'},
        ]
        service, _ = _make_service(threats)

        flags = {t['device_guid']: t['is_new'] for t in service.get_issues()['issues']}

        assert flags == {'new': True, 'old': False, 'nodate': False}


class TestGetIssuesEnrichment:
    """Test suite for device context enrichment"""

    def test_device_info_is_attached_from_cache(self):
        service, _ = _make_service([_threat('g1')])
        service.device_cache.get_device.return_value = {
            'user_email': 'owner@example.com',
            'device_name': 'Pixel 8',
            'platform': 'ANDROID',
            'model': 'Pixel',
        }

        issue = service.get_issues()['issues'][0]

        assert issue['device_info']['owner_email'] == 'owner@example.com'
        assert issue['device_info']['device_name'] == 'Pixel 8'

    def test_api_failure_returns_empty_page(self):
        service, client = _make_service([])
        client.get_threats.side_effect = Exception('boom')

        result = service.get_issues()

        assert result['issues'] == []
        assert result['total'] == 0
        assert result['summary']['total'] == 0
