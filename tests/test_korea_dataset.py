"""Step 2: metadata and mocked requests only, never fetch actual prices."""
import ast
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from research.lab import run_queue, datasets
from services.scanner import eodhd

ROOT = pathlib.Path(__file__).resolve().parents[1]


class KoreaDatasetTests(unittest.TestCase):
    def spec(self):
        return json.loads((ROOT / 'research/lab/queue/data-kr-a-v1.json').read_text())

    def build(self, ds, ensure=None):
        rows = [dict(date='2005-01-03', open=1000, high=1000, low=1000,
                     close=1000, adjusted_close=500, volume=100)]
        with patch.object(datasets, 'manifest', return_value=None), patch.object(eodhd, 'get', return_value=rows) as get, patch.object(datasets, 'save', return_value=('synthetic', {})), patch.object(datasets, 'upload') as upload:
            data, _, _ = (ensure or run_queue.ensure_dataset)(ds, publish=False)
            upload.assert_not_called()
        requests = [(c.args, c.kwargs) for c in get.call_args_list]
        return data, json.dumps(requests, separators=(',', ':')).encode(), requests

    def test_spec_and_approved_membership(self):
        s = self.spec(); ds = s['dataset']
        self.assertEqual((s['kind'], s['criteria'], s['requires']), ('coverage', {'max_missing_share': .05}, ['data-kr-universe-v1']))
        self.assertEqual(ds['id'], 'kr-a-1995-v1')
        self.assertEqual(ds['start'], '1995-01-01')
        self.assertTrue(ds['keep_raw'])
        self.assertEqual(ds['exchanges'], ['KO', 'KQ'])
        self.assertEqual(ds['extra_symbols'], ['069500.KO'])
        kept = (ROOT / ds['symbols_file']).read_text().split()
        self.assertEqual(len(kept), 1531)
        self.assertEqual(len(set(c.split('.')[0] for c in kept)), 1531)
        self.assertFalse(set(c.split('.')[0] for c in kept) & {'006400', '015760', '259960', '307950'})
        result = json.loads((ROOT / 'research/lab/results/data-kr-universe-v1/result.json').read_text())
        self.assertTrue(all(x['code'] in kept for x in result['review_flags']))
        self.assertEqual(len(result['review_flags']), 28)

    def test_all_1532_requests_route_once_and_raw_close_survives(self):
        ds = self.spec()['dataset']
        expected = sorted(set((ROOT / ds['symbols_file']).read_text().split()) | set(ds['extra_symbols']))
        data, _, requests = self.build(ds)
        self.assertEqual(len(requests), 1532)
        self.assertEqual([args[0] for args, _ in requests], ['eod/'+s for s in expected])
        self.assertEqual(set(data['prices']), set(expected))
        self.assertEqual(data['missing_symbols'], [])
        for symbol, (args, params) in zip(expected, requests):
            with self.subTest(symbol=symbol):
                self.assertEqual(params, {'from': '1995-01-01', 'period': 'd'})
                self.assertEqual(args[0].count('.'), 1)
                self.assertEqual(data['prices'][symbol]['raw_close'], [1000.0])
                self.assertEqual(data['prices'][symbol]['close'], [500.0])

    def test_invalid_suffix_stops_before_any_requests(self):
        for symbol in ['000020', '000020.US', '000020.KO.US', '.KO', '000020.ko', '000020.KQ']:
            with self.subTest(symbol=symbol), tempfile.TemporaryDirectory() as folder:
                path = pathlib.Path(folder, 'symbols.txt'); path.write_text('000010.KO\n'+symbol+'\n')
                ds = dict(self.spec()['dataset'], symbols_file=str(path), extra_symbols=[], exchanges=['KO'])
                with patch.object(datasets, 'manifest', return_value=None), patch.object(eodhd, 'get') as get, patch.object(datasets, 'save') as save:
                    with self.assertRaisesRegex(ValueError, 'registered exchange suffix'):
                        run_queue.ensure_dataset(ds, False)
                    get.assert_not_called(); save.assert_not_called()

    def test_invalid_exchange_declaration_is_error(self):
        for value in ['KO', None, [], ['US'], ['KO', 'US']]:
            with self.subTest(exchanges=value), patch.object(datasets, 'manifest', return_value=None), patch.object(eodhd, 'get') as get:
                with self.assertRaisesRegex(ValueError, 'dataset.exchanges'):
                    run_queue.ensure_dataset(dict(self.spec()['dataset'], exchanges=value), False)
                get.assert_not_called()

    def test_legacy_us_hk_requests_byte_identical_to_8afc6d4(self):
        source = subprocess.check_output(['git', 'show', '8afc6d4:research/lab/run_queue.py'], text=True)
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'ensure_dataset')
        namespace = dict(run_queue.__dict__)
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'baseline', 'exec'), namespace)
        for exchange in [None, 'US', 'HK']:
            with self.subTest(exchange=exchange), tempfile.TemporaryDirectory() as folder:
                path = pathlib.Path(folder, 'symbols.txt')
                path.write_text('0700\n0700.HK\n' if exchange == 'HK' else 'AAA\nBRK-B\n')
                ds = dict(id='synthetic', builder='universe', symbols_file=str(path), start='1995-01-01', keep_raw=True, extra_symbols=['2800'] if exchange=='HK' else ['SPY'])
                if exchange is not None:
                    ds['exchange'] = exchange
                old_data, old_bytes, _ = self.build(ds, namespace['ensure_dataset'])
                new_data, new_bytes, _ = self.build(ds)
                self.assertEqual(new_bytes, old_bytes)
                self.assertEqual(json.dumps(new_data).encode(), json.dumps(old_data).encode())


if __name__ == '__main__':
    unittest.main()
