"""Read-only, bounded e-Gov transport diagnostic. Never emits legal candidates."""
import json
import pathlib
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

BASE = 'https://laws.e-gov.go.jp'
IDS = ('503AC0000000060', '504CO0000000024', '504CO0000000025')
MAX_BYTES = 8 * 1024 * 1024
REQUESTS = [('v1_updates_20220119', '/api/1/updatelawlists/20220119'),
            ('v1_updates_20261126', '/api/1/updatelawlists/20261126')]
for law in IDS:
    REQUESTS.extend([(f'v1_{law}', f'/api/1/lawdata/{law}'),
                     (f'v2_history_{law}', f'/api/2/law_revisions/{law}'),
                     (f'v2_body_{law}', f'/api/2/law_data/{law}')])

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def inspect(data, version):
    if version == 'v1':
        if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
            raise ValueError('XML declarations forbidden')
        root = ET.fromstring(data)
        if root.tag != 'DataRoot' or root.findtext('./Result/Code') != '0' or root.find('ApplData') is None:
            raise ValueError('Unexpected XML or API error')
        return {'format': 'XML', 'tags': sorted({e.tag for e in root.iter()})[:200]}
    obj = json.loads(data)
    if not isinstance(obj, dict) or not isinstance(obj.get('law_info'), dict):
        raise ValueError('Unexpected JSON schema')
    return {'format': 'JSON', 'top_level_keys': sorted(obj), 'law_info_keys': sorted(obj['law_info'])}


def probe(name, path, out, opener):
    row = {'name': name, 'url': BASE + path, 'status': 'HOLD', 'transport': 'FAILED'}
    try:
        req = urllib.request.Request(BASE + path, headers={'User-Agent': 'RMS-v09-diagnostic/1.0', 'Accept': 'application/xml' if name.startswith('v1') else 'application/json'}, method='GET')
        with opener.open(req, timeout=15) as response:
            row['http_status'] = response.status
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError('Response exceeds limit')
            (out / (name + '.raw')).write_bytes(data)
            row['bytes'] = len(data)
            if response.status != 200:
                raise ValueError('Unexpected HTTP status')
            row.update(inspect(data, name[:2]))
            row['transport'] = 'PARSED'
    except Exception as exc:
        row['error'] = str(exc)[:500]
    return row


def main():
    out = pathlib.Path('egov-probe-output')
    out.mkdir(exist_ok=False)
    opener = urllib.request.build_opener(NoRedirect())
    rows = []
    for name, path in REQUESTS:
        row = probe(name, path, out, opener)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        time.sleep(1)
    (out / 'report.json').write_text(json.dumps({'status': 'HOLD', 'human_approval_required': True, 'results': rows}, ensure_ascii=False, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
