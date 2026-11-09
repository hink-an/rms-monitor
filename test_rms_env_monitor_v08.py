import json
import tempfile
import unittest
from pathlib import Path
from rms_env_monitor_v08 import SOURCE, validate_fixture


def fixture(ids):
    links = ''.join(f'<a href="{url}">法令関連の記事{i}</a>' for i, url in enumerate(ids))
    return {'schema_version': 1, 'fixture_only': True, 'source_list': SOURCE,
            'legal_change_verified': False, 'html': f'<html><body>{links}</body></html>',
            'expected_candidate_ids': ids}


class SafetyGateTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / 'fixture.json'
        self.ids = [SOURCE + f'test-{i}.html' for i in range(6)]

    def check(self, obj, valid):
        self.path.write_text(json.dumps(obj), encoding='utf-8')
        if valid:
            self.assertEqual(validate_fixture(self.path), set(obj['expected_candidate_ids']))
        else:
            with self.assertRaises(ValueError):
                validate_fixture(self.path)

    def test_normal(self): self.check(fixture(self.ids), True)
    def test_empty_html(self):
        x = fixture(self.ids); x['html'] = ''; self.check(x, False)
    def test_wrong_html(self):
        x = fixture(self.ids); x['html'] = '<html><body>wrong structure</body></html>'; self.check(x, False)
    def test_zero_candidates(self): self.check(fixture([]), False)
    def test_capacity(self): self.check(fixture([SOURCE + f'x{i}' for i in range(10)]), False)
    def test_partial_missing_one(self):
        x = fixture(self.ids); x['html'] = fixture(self.ids[:-1])['html']; self.check(x, False)
    def test_verified_flag(self):
        x = fixture(self.ids); x['legal_change_verified'] = True; self.check(x, False)

if __name__ == '__main__':
    unittest.main()
