#!/usr/bin/env python3
"""Offline fail-closed regression checks for rms_env_monitor_v07.py.

No GitHub credentials, external requests, or changes to the production source.
Run: python3 -m unittest -v test_rms_v07_fail_closed.py
"""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SOURCE = Path(__file__).resolve().with_name('rms_env_monitor_v07.py')
spec = importlib.util.spec_from_file_location('rms_v07_under_test', SOURCE)
rms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rms)


def snapshot():
    return {
        'schema_version': 1,
        'legal_change_verified': False,
        'source_list': 'https://www.env.go.jp/press/',
        'records': [
            {'id': 'urn:offline:test:001', 'review_status': 'UNVERIFIED'},
            {'id': 'urn:offline:test:002', 'review_status': 'UNVERIFIED'},
        ],
    }


def raw(obj):
    return json.dumps(obj, ensure_ascii=False).encode('utf-8')


class SnapshotChecks(unittest.TestCase):
    def test_valid_input_is_accepted(self):
        self.assertEqual(len(rms.load_snapshot(raw(snapshot()), 'test')['records']), 2)

    def test_invalid_json_fails(self):
        with self.assertRaisesRegex(ValueError, 'invalid JSON'):
            rms.load_snapshot(b'{not-json', 'test')

    def test_oversize_json_fails(self):
        with self.assertRaisesRegex(ValueError, 'JSON too large'):
            rms.load_snapshot(b' ' * (rms.MAX_BYTES + 1), 'test')

    def test_bad_schema_fails(self):
        doc = snapshot(); doc['schema_version'] = 2
        with self.assertRaisesRegex(ValueError, 'invalid schema_version'):
            rms.load_snapshot(raw(doc), 'test')

    def test_legal_verification_cannot_be_true(self):
        doc = snapshot(); doc['legal_change_verified'] = True
        with self.assertRaisesRegex(ValueError, 'legal verification must remain false'):
            rms.load_snapshot(raw(doc), 'test')

    def test_unexpected_source_fails(self):
        doc = snapshot(); doc['source_list'] = 'https://untrusted.example/'
        with self.assertRaisesRegex(ValueError, 'unexpected source_list'):
            rms.load_snapshot(raw(doc), 'test')

    def test_missing_or_empty_rows_fail(self):
        for rows in ([], None):
            with self.subTest(rows=rows):
                doc = snapshot(); doc['records'] = rows
                with self.assertRaisesRegex(ValueError, 'records absent/empty'):
                    rms.load_snapshot(raw(doc), 'test')

    def test_duplicate_ids_fail(self):
        doc = snapshot(); doc['records'][1]['id'] = doc['records'][0]['id']
        with self.assertRaisesRegex(ValueError, 'duplicate record IDs'):
            rms.load_snapshot(raw(doc), 'test')

    def test_missing_id_fails(self):
        doc = snapshot(); doc['records'][0]['id'] = ''
        with self.assertRaisesRegex(ValueError, 'record without valid ID'):
            rms.load_snapshot(raw(doc), 'test')

    def test_verified_record_fails(self):
        doc = snapshot(); doc['records'][0]['review_status'] = 'VERIFIED'
        with self.assertRaisesRegex(ValueError, 'record is not unverified'):
            rms.load_snapshot(raw(doc), 'test')


class PreviousArtifactChecks(unittest.TestCase):
    def test_no_baseline_is_error_not_new_zero(self):
        with patch.object(rms, 'api_json', return_value={'workflow_runs': []}):
            with self.assertRaisesRegex(ValueError, 'NO_BASELINE'):
                rms.fetch_previous('example/repo', 'main', 100, 'test-token')

    def test_ambiguous_artifacts_fail(self):
        run = {'id': 10, 'head_branch': 'main', 'conclusion': 'success'}
        artifacts = [{'name': rms.ARTIFACT, 'expired': False}] * 2
        with patch.object(rms, 'api_json', side_effect=[{'workflow_runs': [run]}, {'artifacts': artifacts}]):
            with self.assertRaisesRegex(ValueError, 'Ambiguous previous artifacts'):
                rms.fetch_previous('example/repo', 'main', 100, 'test-token')

    def test_missing_download_url_fails(self):
        run = {'id': 10, 'head_branch': 'main', 'conclusion': 'success'}
        artifact = {'name': rms.ARTIFACT, 'expired': False}
        with patch.object(rms, 'api_json', side_effect=[{'workflow_runs': [run]}, {'artifacts': [artifact]}]):
            with self.assertRaisesRegex(ValueError, 'Missing artifact download URL'):
                rms.fetch_previous('example/repo', 'main', 100, 'test-token')

    def test_unexpected_archive_member_fails(self):
        run = {'id': 10, 'head_branch': 'main', 'conclusion': 'success'}
        artifact = {'name': rms.ARTIFACT, 'expired': False, 'archive_download_url':
                    'https://api.github.com/repos/example/repo/actions/artifacts/1/zip'}
        buff = io.BytesIO()
        with zipfile.ZipFile(buff, 'w') as archive:
            archive.writestr(rms.STATE_MEMBER, raw(snapshot()))
            archive.writestr('unexpected.txt', 'not expected')
        with patch.object(rms, 'api_json', side_effect=[{'workflow_runs': [run]}, {'artifacts': [artifact]}]), \
             patch.object(rms, 'download_artifact', return_value=buff.getvalue()):
            with self.assertRaisesRegex(ValueError, 'Unexpected files'):
                rms.fetch_previous('example/repo', 'main', 100, 'test-token')

    def test_unexpected_download_host_fails_before_network(self):
        with patch.object(rms.urllib.request, 'build_opener', side_effect=AssertionError('network must not run')):
            with self.assertRaisesRegex(ValueError, 'Unexpected artifact download URL'):
                rms.download_artifact('https://untrusted.example/repos/example/repo/actions/artifacts/1/zip',
                                      'example/repo', 'test-token')

    def test_signed_url_does_not_receive_token(self):
        class FakeResponse:
            def __init__(self, status, location=None, payload=b'ZIP'):
                self.status = status
                self.headers = {'Location': location} if location else {}
                self.payload = payload
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, *args): return self.payload

        class FakeOpener:
            def __init__(self): self.requests = []
            def open(self, req, timeout=None):
                self.requests.append(req)
                if len(self.requests) == 1:
                    return FakeResponse(302, 'https://signed-storage.example/download?signature=test')
                return FakeResponse(200, payload=b'ZIP')

        opener = FakeOpener()
        with patch.object(rms.urllib.request, 'build_opener', return_value=opener):
            self.assertEqual(rms.download_artifact(
                'https://api.github.com/repos/example/repo/actions/artifacts/1/zip',
                'example/repo', 'test-token'), b'ZIP')
        self.assertEqual(len(opener.requests), 2)
        self.assertIn('Bearer test-token', opener.requests[0].get_header('Authorization'))
        self.assertIsNone(opener.requests[1].get_header('Authorization'))


class CommandLineChecks(unittest.TestCase):
    def run_program(self, fixture, mode='seed', env=None, existing_output=False):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture_file = root / 'fixture.json'
            fixture_file.write_bytes(fixture)
            outdir = root / 'result'
            if existing_output:
                outdir.mkdir()
            environ = os.environ.copy()
            for key in ('GITHUB_TOKEN', 'GITHUB_REPOSITORY', 'GITHUB_REF_NAME', 'GITHUB_RUN_ID'):
                environ.pop(key, None)
            if env:
                environ.update(env)
            completed = subprocess.run(
                [sys.executable, str(SOURCE), '--mode', mode, '--current', str(fixture_file),
                 '--out-dir', str(outdir)], text=True, capture_output=True, env=environ,
                timeout=10, check=False)
            return completed, outdir.exists(), sorted(p.name for p in outdir.glob('*')) if outdir.exists() else []

    def test_invalid_input_exits_nonzero_without_output(self):
        cp, exists, files = self.run_program(b'{broken')
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn('FAIL-CLOSED:', cp.stderr)
        self.assertFalse(exists)
        self.assertEqual(files, [])

    def test_missing_compare_context_exits_nonzero_without_results(self):
        cp, exists, files = self.run_program(raw(snapshot()), mode='compare')
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn('FAIL-CLOSED:', cp.stderr)
        self.assertEqual(files, [])
        # An empty output directory may have been created before context validation.
        self.assertTrue(exists)

    def test_existing_output_directory_is_not_overwritten(self):
        cp, exists, files = self.run_program(raw(snapshot()), existing_output=True)
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn('refusing overwrite', cp.stderr)
        self.assertTrue(exists)
        self.assertEqual(files, [])

    def test_seed_writes_only_safe_offline_results(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = root / 'fixture.json'; fixture.write_bytes(raw(snapshot()))
            output = root / 'result'
            cp = subprocess.run([sys.executable, str(SOURCE), '--mode', 'seed',
                                 '--current', str(fixture), '--out-dir', str(output)],
                                text=True, capture_output=True, timeout=10, check=False)
            self.assertEqual(cp.returncode, 0, cp.stderr)
            saved = json.loads((output / 'rms-v07-result.json').read_text(encoding='utf-8'))
            self.assertIs(saved['legal_change_verified'], False)
            self.assertIs(saved['offline_test'], True)
            self.assertIs(saved['comparison_performed'], False)
            self.assertEqual(sorted(p.name for p in output.iterdir()),
                             ['rms-v07-result.json', 'rms-v07-state.json'])


if __name__ == '__main__':
    unittest.main()
