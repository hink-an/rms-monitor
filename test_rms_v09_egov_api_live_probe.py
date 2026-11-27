import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock
from rms_v09_egov_api_live_probe import inspect, probe, REQUESTS

class ProbeTests(unittest.TestCase):
    def test_xml(self):
        self.assertEqual(inspect(b'<DataRoot><Result><Code>0</Code></Result><ApplData/></DataRoot>', 'v1')['format'], 'XML')
    def test_xml_error(self):
        with self.assertRaises(ValueError):
            inspect(b'<DataRoot><Result><Code>1</Code></Result><ApplData/></DataRoot>', 'v1')
    def test_entity(self):
        with self.assertRaises(ValueError):
            inspect(b'<!DOCTYPE x><x/>', 'v1')
    def test_json(self):
        self.assertEqual(inspect(b'{"law_info":{}}', 'v2')['format'], 'JSON')
    def test_json_error(self):
        with self.assertRaises(ValueError):
            inspect(b'{"message":"error"}', 'v2')
    def test_html(self):
        with self.assertRaises(ValueError):
            inspect(b'<html/>', 'v1')
    def test_failure_hold(self):
        opener = Mock()
        opener.open.side_effect = OSError('offline')
        with tempfile.TemporaryDirectory() as tmp:
            row = probe('v1_test', '/api/1/test', Path(tmp), opener)
            self.assertEqual(row['status'], 'HOLD')
            self.assertEqual(row['transport'], 'FAILED')
    def test_bounded_scope(self):
        self.assertEqual(len(REQUESTS), 11)
        self.assertTrue(all(p.startswith('/api/') for _, p in REQUESTS))

if __name__ == '__main__':
    unittest.main()
