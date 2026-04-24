import unittest
from unittest.mock import patch

import httpx

from app.services import lsq_client  # noqa: E402
from app.routes.inside_sales import _translate_lsq_error  # noqa: E402


class _FakeAsyncClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    async def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class LsqClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        lsq_client._next_request_slot_at = 0.0

    async def test_rate_limited_request_retries_after_429(self):
        request = httpx.Request('GET', 'https://example.com/lsq')
        client = _FakeAsyncClient([
            httpx.Response(429, headers={'retry-after': '1'}, request=request),
            httpx.Response(200, json={'ok': True}, request=request),
        ])
        sleep_calls: list[float] = []

        async def fake_sleep(delay: float):
            sleep_calls.append(delay)

        with patch.object(lsq_client.asyncio, 'sleep', side_effect=fake_sleep), patch.object(
            lsq_client.time,
            'monotonic',
            return_value=0.0,
        ):
            response = await lsq_client._rate_limited_request(client, 'GET', 'https://example.com/lsq')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(client.requests), 2)
        self.assertIn(1.0, sleep_calls)

    async def test_rate_limited_request_raises_domain_error_after_retry_budget(self):
        request = httpx.Request('GET', 'https://example.com/lsq')
        client = _FakeAsyncClient([
            httpx.Response(429, headers={'retry-after': '2'}, request=request),
            httpx.Response(429, headers={'retry-after': '2'}, request=request),
            httpx.Response(429, headers={'retry-after': '2'}, request=request),
        ])

        async def fake_sleep(_delay: float):
            return None

        with patch.object(lsq_client.asyncio, 'sleep', side_effect=fake_sleep), patch.object(
            lsq_client.time,
            'monotonic',
            return_value=0.0,
        ):
            with self.assertRaises(lsq_client.LsqRateLimitError) as ctx:
                await lsq_client._rate_limited_request(client, 'GET', 'https://example.com/lsq')

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(ctx.exception.retry_after_seconds, 2.0)

    async def test_rate_limited_request_retries_after_connect_error(self):
        request = httpx.Request('GET', 'https://example.com/lsq')
        client = _FakeAsyncClient([
            httpx.ConnectError('dns lookup failed', request=request),
            httpx.Response(200, json={'ok': True}, request=request),
        ])
        sleep_calls: list[float] = []

        async def fake_sleep(delay: float):
            sleep_calls.append(delay)

        with patch.object(lsq_client.asyncio, 'sleep', side_effect=fake_sleep), patch.object(
            lsq_client.time,
            'monotonic',
            return_value=0.0,
        ):
            response = await lsq_client._rate_limited_request(client, 'GET', 'https://example.com/lsq')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(client.requests), 2)
        self.assertIn(1.0, sleep_calls)

    async def test_rate_limited_request_marks_connect_error_retryable_after_retry_budget(self):
        request = httpx.Request('GET', 'https://example.com/lsq')
        client = _FakeAsyncClient([
            httpx.ConnectError('dns lookup failed', request=request),
            httpx.ConnectError('dns lookup failed', request=request),
            httpx.ConnectError('dns lookup failed', request=request),
        ])

        async def fake_sleep(_delay: float):
            return None

        with patch.object(lsq_client.asyncio, 'sleep', side_effect=fake_sleep), patch.object(
            lsq_client.time,
            'monotonic',
            return_value=0.0,
        ):
            with self.assertRaises(lsq_client.LsqRequestError) as ctx:
                await lsq_client._rate_limited_request(client, 'GET', 'https://example.com/lsq')

        self.assertIsNone(ctx.exception.status_code)
        self.assertTrue(ctx.exception.retryable)

    async def test_rate_limited_request_marks_server_errors_retryable_after_retry_budget(self):
        request = httpx.Request('GET', 'https://example.com/lsq')
        client = _FakeAsyncClient([
            httpx.Response(503, request=request),
            httpx.Response(503, request=request),
            httpx.Response(503, request=request),
        ])

        async def fake_sleep(_delay: float):
            return None

        with patch.object(lsq_client.asyncio, 'sleep', side_effect=fake_sleep), patch.object(
            lsq_client.time,
            'monotonic',
            return_value=0.0,
        ):
            with self.assertRaises(lsq_client.LsqRequestError) as ctx:
                await lsq_client._rate_limited_request(client, 'GET', 'https://example.com/lsq')

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertTrue(ctx.exception.retryable)

    def test_translate_lsq_error_maps_rate_limits_to_retryable_http_error(self):
        exc = lsq_client.LsqRateLimitError(url='https://example.com/lsq', retry_after_seconds=2.1)

        http_error = _translate_lsq_error(exc)

        self.assertEqual(http_error.status_code, 503)
        self.assertEqual(http_error.detail, 'LeadSquared rate limit reached. Please retry shortly.')
        self.assertEqual(http_error.headers, {'Retry-After': '3'})


class FetchLeadsFilterContractTests(unittest.IsolatedAsyncioTestCase):
    """fetch_leads must wire ``filter_field`` into LSQ's ``LookupName`` and
    mirror it onto ``Sorting.ColumnName`` by default. This is the entire
    ModifiedOn-delta contract at the HTTP boundary."""

    async def asyncSetUp(self):
        lsq_client._next_request_slot_at = 0.0

    async def _capture(self, *, filter_field=None, sort_field=None):
        import httpx as _httpx

        request = _httpx.Request('POST', 'https://example.com/lsq')
        response = _httpx.Response(200, json=[], request=request)
        captured: dict = {}

        class _AC:
            async def __aenter__(self_):  # noqa: N805
                return self_

            async def __aexit__(self_, *_):  # noqa: N805
                return False

            async def request(self_, method, url, **kwargs):  # noqa: N805
                captured['method'] = method
                captured['url'] = url
                captured['body'] = kwargs.get('json')
                return response

        with patch.object(lsq_client.httpx, 'AsyncClient', lambda *a, **k: _AC()):
            kwargs_out = {}
            if filter_field is not None:
                kwargs_out['filter_field'] = filter_field
            if sort_field is not None:
                kwargs_out['sort_field'] = sort_field
            await lsq_client.fetch_leads(
                date_from='2026-04-20 00:00:00',
                date_to='2026-04-21 00:00:00',
                page=1,
                page_size=50,
                **kwargs_out,
            )
        return captured['body']

    async def test_fetch_leads_defaults_to_createdon_filter_and_sort(self):
        body = await self._capture()
        self.assertEqual(body['Parameter']['LookupName'], 'CreatedOn')
        self.assertEqual(body['Sorting']['ColumnName'], 'CreatedOn')

    async def test_fetch_leads_modifiedon_filter_also_sorts_by_modifiedon(self):
        body = await self._capture(filter_field='ModifiedOn')
        self.assertEqual(body['Parameter']['LookupName'], 'ModifiedOn')
        self.assertEqual(body['Sorting']['ColumnName'], 'ModifiedOn')

    async def test_fetch_leads_explicit_sort_field_overrides_default(self):
        body = await self._capture(filter_field='ModifiedOn', sort_field='CreatedOn')
        self.assertEqual(body['Parameter']['LookupName'], 'ModifiedOn')
        self.assertEqual(body['Sorting']['ColumnName'], 'CreatedOn')

    async def test_fetch_leads_requests_modifiedon_column(self):
        body = await self._capture(filter_field='ModifiedOn')
        # Include_CSV must ask LSQ to return ModifiedOn so the client-side
        # upper-bound filter has data to compare against.
        self.assertIn('ModifiedOn', body['Columns']['Include_CSV'])

    async def test_fetch_leads_client_side_upper_bound_uses_filter_field(self):
        """If filter_field=ModifiedOn, the client-side date_to must filter
        on ModifiedOn (not CreatedOn)."""
        import httpx as _httpx

        request = _httpx.Request('POST', 'https://example.com/lsq')
        inside = {
            'ProspectID': 'p1',
            'CreatedOn': '2025-01-01 00:00:00',
            'ModifiedOn': '2026-04-20 09:00:00',
        }
        outside = {
            'ProspectID': 'p2',
            'CreatedOn': '2025-01-01 00:00:00',
            'ModifiedOn': '2026-04-22 00:00:00',
        }
        response = _httpx.Response(200, json=[inside, outside], request=request)

        class _AC:
            async def __aenter__(self_):  # noqa: N805
                return self_

            async def __aexit__(self_, *_):  # noqa: N805
                return False

            async def request(self_, method, url, **kwargs):  # noqa: N805
                return response

        with patch.object(lsq_client.httpx, 'AsyncClient', lambda *a, **k: _AC()):
            result = await lsq_client.fetch_leads(
                date_from='2026-04-20 00:00:00',
                date_to='2026-04-21 00:00:00',
                filter_field='ModifiedOn',
                page=1,
                page_size=50,
            )
        prospect_ids = [l['ProspectID'] for l in result['leads']]
        self.assertEqual(prospect_ids, ['p1'])


if __name__ == '__main__':
    unittest.main()
