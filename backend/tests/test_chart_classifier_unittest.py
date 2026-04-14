from __future__ import annotations

import unittest

from app.services.chat_engine.chart_classifier import classify_columns, get_eligible_charts


class ClassifyColumnsTests(unittest.TestCase):

    def test_numeric_column(self):
        rows = [{'revenue': 100}, {'revenue': 200.5}, {'revenue': 0}]
        result = classify_columns(['revenue'], rows)
        self.assertEqual(result['revenue'], 'numeric')

    def test_temporal_column_by_name(self):
        rows = [{'created_date': '2026-01-01'}, {'created_date': '2026-02-01'}]
        result = classify_columns(['created_date'], rows)
        self.assertEqual(result['created_date'], 'temporal')

    def test_temporal_column_by_value(self):
        rows = [{'ts': '2026-01-15T10:00:00'}, {'ts': '2026-02-20T12:00:00'}]
        result = classify_columns(['ts'], rows)
        self.assertEqual(result['ts'], 'temporal')

    def test_categorical_column(self):
        rows = [{'agent': 'Alice'}, {'agent': 'Bob'}]
        result = classify_columns(['agent'], rows)
        self.assertEqual(result['agent'], 'categorical')

    def test_ordered_categorical_from_dimension_metadata(self):
        rows = [{'stage': 'new'}, {'stage': 'closed'}]
        dimensions = [{'name': 'stage', 'ordering': ['new', 'contacted', 'closed']}]
        result = classify_columns(['stage'], rows, dimensions=dimensions)
        self.assertEqual(result['stage'], 'ordered_categorical')

    def test_mixed_columns(self):
        rows = [
            {'agent': 'Alice', 'revenue': 100, 'month': '2026-01'},
            {'agent': 'Bob', 'revenue': 200, 'month': '2026-02'},
        ]
        result = classify_columns(['agent', 'revenue', 'month'], rows)
        self.assertEqual(result['agent'], 'categorical')
        self.assertEqual(result['revenue'], 'numeric')
        self.assertEqual(result['month'], 'temporal')

    def test_empty_rows_all_categorical(self):
        result = classify_columns(['a', 'b'], [])
        self.assertEqual(result['a'], 'categorical')
        self.assertEqual(result['b'], 'categorical')

    def test_null_values_skipped(self):
        rows = [{'count': None}, {'count': 5}, {'count': 10}]
        result = classify_columns(['count'], rows)
        self.assertEqual(result['count'], 'numeric')


class GetEligibleChartsTests(unittest.TestCase):

    def test_one_categorical_one_numeric(self):
        column_types = {'agent': 'categorical', 'revenue': 'numeric'}
        eligible = get_eligible_charts(column_types, row_count=5)
        self.assertIn('bar', eligible)
        self.assertIn('horizontal_bar', eligible)
        self.assertIn('pie', eligible)
        self.assertNotIn('line', eligible)
        self.assertNotIn('scatter', eligible)

    def test_one_temporal_one_numeric(self):
        column_types = {'month': 'temporal', 'revenue': 'numeric'}
        eligible = get_eligible_charts(column_types, row_count=12)
        self.assertIn('line', eligible)
        self.assertIn('area', eligible)
        self.assertIn('bar', eligible)
        self.assertNotIn('funnel', eligible)

    def test_ordered_categorical_enables_funnel(self):
        column_types = {'stage': 'ordered_categorical', 'count': 'numeric'}
        eligible = get_eligible_charts(column_types, row_count=6)
        self.assertIn('funnel', eligible)
        # Funnel should rank first due to specificity
        self.assertEqual(eligible[0], 'funnel')

    def test_two_numerics_enables_scatter(self):
        column_types = {'revenue': 'numeric', 'calls': 'numeric'}
        eligible = get_eligible_charts(column_types, row_count=50)
        self.assertIn('scatter', eligible)

    def test_pie_excluded_for_high_row_count(self):
        column_types = {'agent': 'categorical', 'revenue': 'numeric'}
        eligible = get_eligible_charts(column_types, row_count=20)
        self.assertNotIn('pie', eligible)
        self.assertNotIn('donut', eligible)

    def test_radar_excluded_for_high_row_count(self):
        column_types = {'dim': 'categorical', 'val': 'numeric'}
        eligible = get_eligible_charts(column_types, row_count=15)
        self.assertNotIn('radar', eligible)

    def test_radar_included_for_low_row_count(self):
        column_types = {'dim': 'categorical', 'val': 'numeric'}
        eligible = get_eligible_charts(column_types, row_count=6)
        self.assertIn('radar', eligible)

    def test_multi_numeric_enables_stacked_and_composed(self):
        column_types = {'month': 'temporal', 'rev': 'numeric', 'cost': 'numeric'}
        eligible = get_eligible_charts(column_types, row_count=10)
        self.assertIn('stacked_area', eligible)
        self.assertIn('composed', eligible)
        self.assertIn('line', eligible)

    def test_ordered_categorical_satisfies_ordinal(self):
        """ordered_categorical columns should satisfy min_ordinal for line/area."""
        column_types = {'stage': 'ordered_categorical', 'count': 'numeric'}
        eligible = get_eligible_charts(column_types, row_count=6)
        self.assertIn('line', eligible)
        self.assertIn('area', eligible)

    def test_empty_columns_returns_empty(self):
        eligible = get_eligible_charts({}, row_count=0)
        self.assertEqual(eligible, [])

    def test_horizontal_bar_preferred_for_high_cardinality(self):
        column_types = {'city': 'categorical', 'sales': 'numeric'}
        eligible = get_eligible_charts(column_types, row_count=15)
        bar_idx = eligible.index('bar')
        hbar_idx = eligible.index('horizontal_bar')
        self.assertLess(hbar_idx, bar_idx)

    def test_horizontal_bar_not_preferred_for_low_cardinality(self):
        column_types = {'status': 'categorical', 'count': 'numeric'}
        eligible = get_eligible_charts(column_types, row_count=3)
        bar_idx = eligible.index('bar')
        hbar_idx = eligible.index('horizontal_bar')
        self.assertLess(bar_idx, hbar_idx)
