from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests
import collection_health
import scrape


class CollectionHealthTests(unittest.TestCase):
    def test_schedule_guard_and_manual_override(self):
        now = datetime(2026, 11, 19, 12, tzinfo=timezone.utc)
        for hours, expected in ((0, False), (2.99, False), (3, True), (12, True), (-1, True)):
            status = {'last_successful_collection_at_utc': (now-timedelta(hours=hours)).isoformat()}
            self.assertEqual(collection_health.collection_due(status, 'schedule', now)[0], expected)
            self.assertTrue(collection_health.collection_due(status, 'workflow_dispatch', now)[0])
        for broken in ({}, [], {'last_successful_collection_at_utc':'bad'}):
            self.assertTrue(collection_health.collection_due(broken, 'schedule', now)[0])

    def test_failed_validation_cannot_advance_heartbeat(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'status.json';path.write_text('{"previous":"heartbeat"}')
            before=path.read_bytes()
            with patch.object(collection_health,'check',side_effect=ValueError('missing records')):
                with self.assertRaises(ValueError): collection_health.record_success(path)
            self.assertEqual(path.read_bytes(),before)

    def test_success_heartbeat_is_distinct_from_latest_post_date(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'status.json'
            with patch.object(collection_health,'check',return_value=([],{'newest_post_utc':'2026-01-01T00:00:00Z'})):
                result=collection_health.record_success(path)
            self.assertNotEqual(result['last_successful_collection_at_utc'],result['archive_validation']['newest_post_utc'])
            self.assertEqual(json.loads(path.read_text()),result)


class ProxyRetryTests(unittest.TestCase):
    @patch.object(scrape.time,'sleep')
    def test_transient_failure_retries_and_closes_session(self,sleep):
        session=Mock(); response=Mock(); response.json.return_value=[{'id':'1'}]
        session.get.side_effect=[requests.Timeout(),response]
        with patch.object(scrape.requests,'Session',return_value=session),patch.object(scrape,'SCRAPEOPS_API_KEY','test'):
            self.assertEqual(scrape.scrape('https://example.test'),[{'id':'1'}])
        self.assertEqual(session.get.call_count,2);sleep.assert_called_once_with(5);session.close.assert_called_once()

    @patch.object(scrape.time,'sleep')
    def test_exhausted_retries_raise(self,sleep):
        session=Mock();session.get.side_effect=requests.Timeout()
        with patch.object(scrape.requests,'Session',return_value=session),patch.object(scrape,'SCRAPEOPS_API_KEY','test'):
            with self.assertRaises(requests.Timeout): scrape.scrape('https://example.test')
        self.assertEqual(session.get.call_count,3);self.assertEqual(sleep.call_count,2)

    @patch.object(scrape.time,'sleep')
    def test_authentication_failure_is_not_retried(self,sleep):
        session=Mock();response=requests.Response();response.status_code=401
        session.get.side_effect=requests.HTTPError(response=response)
        with patch.object(scrape.requests,'Session',return_value=session),patch.object(scrape,'SCRAPEOPS_API_KEY','test'):
            with self.assertRaises(requests.HTTPError): scrape.scrape('https://example.test')
        self.assertEqual(session.get.call_count,1);sleep.assert_not_called()


if __name__=='__main__': unittest.main()
