import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.routes.analytics_library import (
    ChartConfigIn,
    SaveChartRequest,
    SaveDashboardRequest,
    save_chart,
    save_dashboard,
)


class AnalyticsLibraryRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_save_chart_persists_source_session_lineage(self):
        auth = SimpleNamespace(
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
        )
        db = AsyncMock()
        db.add = Mock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        with patch('app.routes.analytics_library.ensure_registered_app_access', new=AsyncMock()):
            payload = await save_chart(
                SaveChartRequest(
                    appId='kaira-bot',
                    title='Pass rate',
                    sqlQuery='select 1',
                    chartConfig=ChartConfigIn(type='bar', xKey='week', yKey='value'),
                    sourceQuestion='show pass rate',
                    sourceSessionId='8d7d7d56-5dca-4f6a-a2c6-4cb5f6f8e221',
                ),
                auth=auth,
                db=db,
            )

        saved_chart = db.add.call_args.args[0]
        self.assertEqual(str(saved_chart.source_session_id), '8d7d7d56-5dca-4f6a-a2c6-4cb5f6f8e221')
        self.assertEqual(payload['sourceSessionId'], '8d7d7d56-5dca-4f6a-a2c6-4cb5f6f8e221')

    async def test_save_dashboard_persists_source_session_lineage(self):
        auth = SimpleNamespace(
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
        )
        db = AsyncMock()
        db.add = Mock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        with patch('app.routes.analytics_library.ensure_registered_app_access', new=AsyncMock()), patch(
            'app.routes.analytics_library._get_readable_chart',
            new=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
        ):
            payload = await save_dashboard(
                SaveDashboardRequest(
                    appId='kaira-bot',
                    title='Weekly dashboard',
                    chartIds=['chart-1', 'chart-2'],
                    sourceSessionId='8d7d7d56-5dca-4f6a-a2c6-4cb5f6f8e221',
                ),
                auth=auth,
                db=db,
            )

        saved_dashboard = db.add.call_args.args[0]
        self.assertEqual(str(saved_dashboard.source_session_id), '8d7d7d56-5dca-4f6a-a2c6-4cb5f6f8e221')
        self.assertEqual(payload['sourceSessionId'], '8d7d7d56-5dca-4f6a-a2c6-4cb5f6f8e221')
