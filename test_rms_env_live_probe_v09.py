import tempfile
import unittest
from pathlib import Path
import rms_env_live_probe_v09 as m


def fixture(n):
    links = ''.join(f'<a href="/press/item{i}.html">公布のお知らせ{i}</a>' for i in range(n))
    return ('<html><body>' + links + '</body></html>').encode()


class SafetyTests(unittest.TestCase):
    def test_100(self):
        result = m.analyze(fixture(100))
        self.assertEqual(result['article_shape_candidates'], 100)
        self.assertFalse(result['limit_exceeded'])
        self.assertFalse(result['comparison_allowed'])

    def test_101_not_truncated(self):
        result = m.analyze(fixture(101))
        self.assertEqual(len(result['candidate_inventory']), 101)
        self.assertTrue(result['limit_exceeded'])
        self.assertEqual(result['over_limit_count'], 1)

    def test_duplicate(self):
        data = b'<html><body><a href="/press/x.html">x</a><a href="/press/x.html?x=2">x</a></body></html>'
        result = m.analyze(data)
        self.assertEqual(result['duplicate_article_urls'], 1)

    def test_bad_input(self):
        for value in [b'', b'broken', b'\xff', b'a' * (m.MAX_BYTES+1)]:
            with self.subTest(value=value[:8]):
                with self.assertRaises((UnicodeError, ValueError)):
                    m.analyze(value)

    def test_reference_not_formal(self):
        data = b'<html><body><a href="/press/x.html">example</a></body></html>'
        self.assertEqual(m.analyze(data)['candidate_inventory'][0]['queue'], 'OTHER_UNVERIFIED')
        self.assertEqual(m.label_title('指定案の審議会'), 'REFERENCE_CANDIDATE_UNVERIFIED')

    def test_refuse_existing_output(self):
        with tempfile.TemporaryDirectory() as d:
            html = Path(d) / 'input.html'
            output = Path(d) / 'existing.json'
            html.write_bytes(fixture(1))
            output.write_text('DO NOT CHANGE', encoding='utf-8')
            self.assertEqual(m.main(['--offline-html', str(html), '--output', str(output)]), 2)
            self.assertEqual(output.read_text(encoding='utf-8'), 'DO NOT CHANGE')

    def test_no_foreign_host(self):
        for url in ['https://example.org/press/x.html', 'http://www.env.go.jp/press/x.html',
                    'https://www.env.go.jp.evil.com/press/x.html']:
            self.assertIsNone(m.normalize_article(url))


if __name__ == '__main__':
    unittest.main(verbosity=2)
