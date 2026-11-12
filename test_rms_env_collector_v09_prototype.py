import tempfile
import unittest
from pathlib import Path
from rms_env_collector_v09_prototype import analyze, main

def make_html(n):
    parts = ['<html><body>']
    for i in range(n):
        title = '省令の公布について' if i % 2 == 0 else '指定案について'
        parts.append(f'<a href="/press/press_{i:05d}.html">{title}</a>')
    return (''.join(parts) + '</body></html>').encode('utf-8')

class PrototypeTest(unittest.TestCase):
    def test_100_under_limit(self):
        r = analyze(make_html(100))
        self.assertFalse(r['limit_exceeded'])
        self.assertEqual(r['article_shape_candidates'], 100)
        self.assertFalse(r['comparison_allowed'])
        self.assertEqual(r['diagnostic_status'], 'HOLD')
    def test_101_alert_without_silent_truncation(self):
        r = analyze(make_html(101))
        self.assertTrue(r['limit_exceeded'])
        self.assertEqual(len(r['candidate_inventory']), 101)
        self.assertEqual(r['unexamined_due_to_limit'], 1)
    def test_duplicate(self):
        raw = make_html(1).replace(b'</body>', b'<a href="/press/press_00000.html">again</a></body>')
        self.assertEqual(analyze(raw)['duplicate_article_urls'], 1)
    def test_reference_vs_formal(self):
        r = analyze(make_html(2))
        self.assertEqual(r['queue_counts']['FORMAL_REVIEW_CANDIDATE_UNVERIFIED'], 1)
        self.assertEqual(r['queue_counts']['REFERENCE_CANDIDATE_UNVERIFIED'], 1)
    def test_malformed_and_oversize(self):
        with self.assertRaises(ValueError): analyze(b'')
        with self.assertRaises(ValueError): analyze(b'\xff')
        with self.assertRaises(ValueError): analyze(b'x' * (2*1024*1024+1))
    def test_exclusive_output(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            src, dst = p/'in.html', p/'out.json'
            src.write_bytes(make_html(2))
            self.assertEqual(main(['--offline-html',str(src),'--output',str(dst)]),0)
            before = dst.read_bytes()
            self.assertEqual(main(['--offline-html',str(src),'--output',str(dst)]),1)
            self.assertEqual(dst.read_bytes(),before)

if __name__ == '__main__': unittest.main()
