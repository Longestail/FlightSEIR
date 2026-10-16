"""Synthetic regression tests; run: python -m unittest discover -s tests -v."""
import copy
import logging
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src' / 'data'))
import construct_edge_list as edges


class FlightNetworkTests(unittest.TestCase):
    def setUp(self):
        airports = pd.DataFrame([
            {'iata': 'YYZ', 'city': 'Toronto', 'country': 'Canada'},
            {'iata': 'YVR', 'city': 'Vancouver', 'country': 'Canada'},
            {'iata': 'JFK', 'city': 'New York', 'country': 'United States'},
        ], index=[10, 20, 30])
        state = patch.multiple(edges, airports=airports, use_country=False,
                               flight_network_by_date={}, create=True)
        state.start()
        self.addCleanup(state.stop)

    def flight(self, **changes):
        record = dict(status='landed', departure_date=20200101,
                      departure_airport='YYZ', arrival_airport='JFK',
                      flight_number='TEST1')
        record.update(changes)
        return record

    def test_legitimate_city_and_country_mappings(self):
        self.assertEqual(edges.to_node_id('YYZ'), 'Toronto')
        self.assertEqual(edges.to_node_id('YVR'), 'Vancouver')
        self.assertEqual(edges.to_node_id('JFK'), 'United States')
        edges.use_country = True
        self.assertEqual(edges.to_node_id('YYZ'), 'Canada')
        self.assertEqual(edges.to_node_id('JFK'), 'United States')

    def test_unknown_and_nonexact_codes_raise(self):
        for code in ['XXXX', 'ZZZ', 'yyz', ' YYZ', 'YYZ ']:
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, 'Unrecognized IATA'):
                edges.to_node_id(code)

    def test_missing_and_nonstrings_raise_even_with_missing_reference(self):
        edges.airports.loc[40] = [None, 'Invalid', 'Canada']
        for code in [None, float('nan'), pd.NA, '', '  ', 123, ['YYZ']]:
            with self.subTest(code=repr(code)), self.assertRaisesRegex(ValueError, 'Missing or invalid IATA'):
                edges.to_node_id(code)

    def test_empty_reference_table_raises(self):
        edges.airports = edges.airports.iloc[:0]
        with self.assertRaisesRegex(ValueError, 'Unrecognized IATA'):
            edges.to_node_id('YYZ')

    def test_duplicate_codes_keep_first_match(self):
        edges.airports.loc[40] = ['YYZ', 'Other city', 'Canada']
        self.assertEqual(edges.to_node_id('YYZ'), 'Toronto')

    def test_duplicate_index_labels_do_not_select_unmatched_rows(self):
        edges.airports.index = [1, 1, 1]
        self.assertEqual(edges.to_node_id('YVR'), 'Vancouver')

    def test_invalid_endpoint_leaves_network_unchanged(self):
        for existing in [False, True]:
            for endpoint in ['departure_airport', 'arrival_airport']:
                for code in ['XXXX', None, '']:
                    with self.subTest(existing=existing, endpoint=endpoint, code=code):
                        edges.flight_network_by_date = {}
                        if existing:
                            edges.append_flight_to_network(self.flight())
                        before = copy.deepcopy(edges.flight_network_by_date)
                        with self.assertRaises(ValueError):
                            edges.append_flight_to_network(self.flight(**{endpoint: code}))
                        self.assertEqual(edges.flight_network_by_date, before)

    def test_build_preserves_counts_dates_direction_and_status_filter(self):
        records = [self.flight(), self.flight(status='diverted'),
                   self.flight(departure_date=20200102),
                   self.flight(departure_airport='JFK', arrival_airport='YYZ'),
                   self.flight(status='cancelled', departure_airport=None)]
        with patch.multiple(edges, historic_flights=pd.DataFrame(records),
                            count_by_flight_status={},
                            default_logger=logging.getLogger('test'), create=True):
            edges.build_flight_network()
            self.assertEqual(edges.count_by_flight_status,
                             {'landed': 3, 'diverted': 1, 'cancelled': 1})
        self.assertEqual(edges.flight_network_by_date, {
            20200101: {('Toronto', 'United States'): 2, ('United States', 'Toronto'): 1},
            20200102: {('Toronto', 'United States'): 1}})

    def test_country_mode_retains_self_edges(self):
        edges.use_country = True
        edges.append_flight_to_network(self.flight(arrival_airport='YVR'))
        self.assertEqual(edges.flight_network_by_date,
                         {20200101: {('Canada', 'Canada'): 1}})


if __name__ == '__main__':
    unittest.main()
