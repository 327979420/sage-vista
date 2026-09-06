from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import hashlib
import json
import unittest
from unittest.mock import patch

from services.market_data.eodhd_membership import (
    KNOWN_EXCHANGES, KNOWN_TYPES, MembershipSourceError, parse_us_symbol_response,
)
from services.scanner.audit_eodhd import PRIMARY, common

START = datetime(2026, 9, 8, 23, 47, tzinfo=timezone.utc)
END = datetime(2026, 9, 9, 3, 59, tzinfo=timezone.utc)


def row(code='AAPL', **changes):
    return {'Code': code, 'Exchange': 'NASDAQ', 'Type': 'Common Stock',
            'Name': 'Synthetic company', 'Country': 'USA', 'Currency': 'USD', 'Isin': None, **changes}


def parse(rows, **changes):
    raw = rows if type(rows) is bytes else json.dumps(rows, ensure_ascii=False).encode()
    return parse_us_symbol_response(raw, **{'as_of': '2026-09-08', 'started_at': START,
                                           'completed_at': END, **changes})


class MembershipTests(unittest.TestCase):
    def test_raw_bytes_and_full_partition_are_preserved(self):
        rows = [row(), row('FUND', Type='ETF'), row('PINKCO', Exchange='PINK')]
        rows[0]['Extra'] = {'provider_metadata': '原文'}
        raw = (json.dumps(rows, ensure_ascii=False, indent=2) + '\n').encode()
        value = parse(raw)
        self.assertEqual(value.raw_bytes, raw)
        self.assertEqual(value.raw_sha256, 'sha256:' + hashlib.sha256(raw).hexdigest())
        self.assertEqual(value.raw_count, 3)
        self.assertEqual([s.provider_code for s in value.included], ['AAPL'])
        self.assertEqual({s.symbol.provider_code: s.reason for s in value.excluded},
                         {'FUND': 'not_common_stock', 'PINKCO': 'outside_primary_exchanges'})
        self.assertEqual(len(value.included) + len(value.excluded), value.raw_count)
        self.assertFalse(hasattr(value, 'complete'))
        self.assertFalse(hasattr(value, 'universe_id'))
        self.assertIsNone(value.included[0].isin)

    def test_all_recognized_types_and_venues_reuse_existing_filter(self):
        rows = [row(f'S{i}', Exchange=exchange, Type=kind)
                for i, (exchange, kind) in enumerate((e, k) for e in sorted(KNOWN_EXCHANGES) for k in sorted(KNOWN_TYPES))]
        result = parse(rows)
        self.assertEqual({s.provider_code for s in result.included}, {s['Code'] for s in common(rows)})
        self.assertEqual({s.exchange for s in result.included}, PRIMARY)
        self.assertEqual(result.raw_count, len(rows))
        self.assertEqual(len(result.included) + len(result.excluded), len(rows))

    def test_members_are_immutable_and_not_truncated_to_cache_target(self):
        result = parse([row(f'S{i}') for i in range(1001)])
        self.assertEqual(len(result.included), 1001)
        with self.assertRaises(FrozenInstanceError): result.as_of = '2026-09-09'
        with self.assertRaises(FrozenInstanceError): result.included[0].provider_code = 'changed'
        with self.assertRaises(TypeError): result.included[0] = None

    def test_order_and_format_change_raw_hash_not_selection_facts(self):
        rows = [row('B'), row('A'), row('F', Type='FUND')]
        first, second = parse(rows), parse(list(reversed(rows)))
        self.assertEqual(first.included, second.included)
        self.assertEqual(first.excluded, second.excluded)
        self.assertNotEqual(first.raw_sha256, second.raw_sha256)
        self.assertNotEqual(first.raw_sha256, parse((json.dumps(rows, indent=2) + '\n').encode()).raw_sha256)

    def test_observed_new_york_date_is_required_at_both_ends_including_dst(self):
        self.assertEqual(parse([row()]).as_of, '2026-09-08')  # UTC spans two dates.
        invalid = [dict(as_of='2026-09-09'), dict(completed_at=END + timedelta(minutes=1)),
                   dict(started_at=START - timedelta(days=1)), dict(completed_at=START - timedelta(seconds=1)),
                   dict(started_at=START.replace(tzinfo=None)), dict(completed_at='2026-09-09T03:59:00Z'),
                   dict(as_of='2026-9-8'), dict(started_at=START.astimezone(timezone(timedelta(hours=10))))]
        for change in invalid:
            with self.subTest(change=change), self.assertRaisesRegex(MembershipSourceError, 'observation_date_invalid'):
                parse([row()], **change)
        winter = dict(as_of='2026-01-06', started_at=datetime(2026, 1, 6, 23, tzinfo=timezone.utc),
                      completed_at=datetime(2026, 1, 7, 4, 59, tzinfo=timezone.utc))
        self.assertEqual(parse([row()], **winter).as_of, '2026-01-06')
        winter['completed_at'] += timedelta(minutes=1)
        with self.assertRaises(MembershipSourceError): parse([row()], **winter)

    def test_empty_truncated_duplicate_json_keys_and_nonfinite_rejected(self):
        for raw in [b'', b'[]', b'{}', b'[', b'[{"Code":"A","Code":"B"}]', b'null', b'\xff',
                    b'[{"x":NaN}]', b'[{"x":Infinity}]', b'[{"x":1e10000}]', b'[null]', b'[{"x":"\\ud800"}]']:
            with self.subTest(raw=raw), self.assertRaises(MembershipSourceError): parse(raw)
        with patch('services.market_data.eodhd_membership.MAX_RESPONSE_BYTES', 1):
            with self.assertRaisesRegex(MembershipSourceError, 'size_invalid'): parse([row()])
        with self.assertRaisesRegex(MembershipSourceError, 'size_invalid'):
            parse_us_symbol_response(bytearray(b'[]'), as_of='2026-09-08', started_at=START, completed_at=END)

    def test_missing_and_invalid_fields_fail_even_for_excluded_rows(self):
        for key in ('Code', 'Exchange', 'Type', 'Name', 'Country', 'Currency'):
            for value in (None, '', ' whitespace ', 42, True, 'a\x00b'):
                with self.subTest(key=key, value=value), self.assertRaises(MembershipSourceError):
                    parse([row(), row('EXCLUDED', Type='ETF', **{key: value})] if key != 'Type'
                          else [row(), row('EXCLUDED', Type=value)])
        with self.assertRaises(MembershipSourceError): parse([row(Isin=0)])
        self.assertEqual(parse([row(Isin='US0123456789')]).included[0].isin, 'US0123456789')

    def test_unknown_vocabulary_and_code_collisions_do_not_become_exclusions(self):
        for bad in [row('X', Exchange='UNKNOWN'), row('X', Type='UNKNOWN'), row('X', Type='common_stock'),
                    row(), row(Exchange='NYSE'), row(Type='ETF')]:
            with self.subTest(bad=bad), self.assertRaises(MembershipSourceError): parse([row(), bad])
        with self.assertRaisesRegex(MembershipSourceError, 'primary_common_empty'):
            parse([row('F', Type='ETF'), row('P', Exchange='PINK')])

    def test_parser_has_no_io_and_errors_do_not_expose_private_payload(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')), \
             patch('builtins.open', side_effect=AssertionError('file write forbidden')):
            self.assertEqual(parse([row()]).raw_count, 1)
            with self.assertRaises(MembershipSourceError) as caught:
                parse([row(Type='private-token-body')])
            self.assertNotIn('private-token-body', str(caught.exception))


if __name__ == '__main__': unittest.main()
