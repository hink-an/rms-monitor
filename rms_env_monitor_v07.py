#!/usr/bin/env python3
"""RMS Monitor v0.7: isolated offline cross-run snapshot handoff.

No government requests. Does not alter production files or repository contents.
"""
import argparse
import datetime as dt
import io
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

WORKFLOW = 'rms-monitor-v07-handoff.yml'
ARTIFACT = 'rms-v07-validated-state'
STATE_MEMBER = 'rms-v07-state.json'
MAX_BYTES = 2_000_000


def load_snapshot(raw, label):
    if len(raw) > MAX_BYTES:
        raise ValueError(f'{label}: JSON too large')
    try:
        obj = json.loads(raw.decode('utf-8-sig'))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f'{label}: invalid JSON: {exc}') from exc
    if not isinstance(obj, dict) or obj.get('schema_version') != 1:
        raise ValueError(f'{label}: invalid schema_version')
    if obj.get('legal_change_verified') is not False:
        raise ValueError(f'{label}: legal verification must remain false')
    if obj.get('source_list') != 'https://www.env.go.jp/press/':
        raise ValueError(f'{label}: unexpected source_list')
    rows = obj.get('records')
    if not isinstance(rows, list) or not rows:
        raise ValueError(f'{label}: records absent/empty; cannot compare')
    ids = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id']:
            raise ValueError(f'{label}: record without valid ID')
        if row.get('review_status') not in ('UNVERIFIED', '未確認'):
            raise ValueError(f'{label}: record is not unverified')
        ids.append(row['id'])
    if len(set(ids)) != len(ids):
        raise ValueError(f'{label}: duplicate record IDs')
    return obj


def api_json(url, token):
    req = urllib.request.Request(url, headers={
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'rms-monitor-v07',
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('GitHub API response too large')
    return json.loads(data)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download_artifact(download_url, repo, token):
    """Read the authenticated API redirect, then download without forwarding token."""
    parsed = urllib.parse.urlsplit(download_url)
    prefix = f'/repos/{repo}/actions/artifacts/'
    if (parsed.scheme != 'https' or parsed.hostname != 'api.github.com'
            or parsed.username or parsed.password or parsed.port is not None
            or not parsed.path.startswith(prefix) or not parsed.path.endswith('/zip')
            or parsed.query or parsed.fragment):
        raise ValueError('Unexpected artifact download URL')

    no_redirect = urllib.request.build_opener(NoRedirect())
    api_request = urllib.request.Request(download_url, headers={
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'rms-monitor-v07',
    })
    try:
        with no_redirect.open(api_request, timeout=30) as response:
            status = response.status
            location = response.headers.get('Location')
    except urllib.error.HTTPError as exc:
        status = exc.code
        location = exc.headers.get('Location')
        exc.close()
    if status != 302 or not location:
        raise ValueError(f'Artifact API expected HTTP 302, got {status}')

    signed = urllib.parse.urlsplit(location)
    if (signed.scheme != 'https' or not signed.hostname
            or signed.username or signed.password or signed.port is not None
            or signed.hostname == 'api.github.com' or signed.fragment):
        raise ValueError('Unexpected signed artifact download location')
    # Never forward the GitHub token to the signed storage URL.
    signed_request = urllib.request.Request(location, headers={
        'User-Agent': 'rms-monitor-v07',
    })
    with no_redirect.open(signed_request, timeout=30) as response:
        if response.status != 200:
            raise ValueError(f'Signed ZIP expected HTTP 200, got {response.status}')
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('Artifact archive too large')
    return data


def fetch_previous(repo, branch, current_run_id, token):
    safe_repo = urllib.parse.quote(repo, safe='/')
    url = (f'https://api.github.com/repos/{safe_repo}/actions/workflows/{WORKFLOW}/runs'
           f'?branch={urllib.parse.quote(branch)}&event=workflow_dispatch&status=success&per_page=50')
    runs = api_json(url, token).get('workflow_runs', [])
    for run in runs:
        if run.get('id') == current_run_id or run.get('id', 0) > current_run_id:
            continue
        if run.get('head_branch') != branch or run.get('conclusion') != 'success':
            continue
        artifacts_url = f'https://api.github.com/repos/{safe_repo}/actions/runs/{run["id"]}/artifacts?per_page=100'
        artifacts = api_json(artifacts_url, token).get('artifacts', [])
        eligible = [a for a in artifacts if a.get('name') == ARTIFACT and not a.get('expired')]
        if not eligible:
            continue
        if len(eligible) != 1:
            raise ValueError('Ambiguous previous artifacts')
        download = eligible[0].get('archive_download_url')
        if not download:
            raise ValueError('Missing artifact download URL')
        data = download_artifact(download, repo, token)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if set(archive.namelist()) != {STATE_MEMBER, 'rms-v07-result.json'} or len(archive.infolist()) != 2:
                raise ValueError('Unexpected files in previous artifact')
            info = archive.getinfo(STATE_MEMBER)
            if info.file_size > MAX_BYTES:
                raise ValueError('Previous snapshot too large')
            previous = load_snapshot(archive.read(info), 'previous artifact')
        return previous, run['id']
    raise ValueError('NO_BASELINE: no eligible previous successful v0.7 artifact (not new=0)')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['seed', 'compare'], required=True)
    parser.add_argument('--current', required=True)
    parser.add_argument('--out-dir', default='v07-output')
    args = parser.parse_args()
    output = Path(args.out_dir)
    if output.exists():
        raise ValueError('Output directory already exists: refusing overwrite')
    current = load_snapshot(Path(args.current).read_bytes(), 'current fixture')
    output.mkdir(parents=True, exist_ok=False)
    result = {
        'schema_version': 1,
        'monitor_version': '0.7',
        'captured_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'offline_test': True,
        'legal_change_verified': False,
        'current_count': len(current['records']),
    }
    if args.mode == 'seed':
        result.update({'status': 'BASELINE_CREATED', 'comparison_performed': False,
                       'note': 'Manual seed from repository fixture; not a live retrieval.'})
    else:
        token = os.getenv('GITHUB_TOKEN', '')
        repo = os.getenv('GITHUB_REPOSITORY', '')
        branch = os.getenv('GITHUB_REF_NAME', '')
        run_id = int(os.getenv('GITHUB_RUN_ID', '0'))
        if not token or not repo or branch != 'main' or not run_id:
            raise ValueError('Missing or invalid GitHub context')
        previous, source_run = fetch_previous(repo, branch, run_id, token)
        old_ids = {x['id'] for x in previous['records']}
        new_ids = {x['id'] for x in current['records']}
        result.update({'status': 'COMPARED', 'comparison_performed': True,
                       'previous_run_id': source_run,
                       'new_candidate_ids': sorted(new_ids - old_ids),
                       'unchanged_ids': sorted(new_ids & old_ids),
                       'removed_from_current_list_ids': sorted(old_ids - new_ids),
                       'note': 'ID comparison only; disappearance is NOT repeal.'})
    # The next-run state is always the validated current fixture, never an output from a prior run.
    (output / STATE_MEMBER).write_text(json.dumps(current, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (output / 'rms-v07-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"PASS: {result['status']}; current={result['current_count']}; verified=false")
    if result['comparison_performed']:
        print(f"PASS: source_run={result['previous_run_id']}, new={len(result['new_candidate_ids'])}, "
              f"unchanged={len(result['unchanged_ids'])}, absent={len(result['removed_from_current_list_ids'])}")


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'FAIL-CLOSED: {exc}', file=sys.stderr)
        sys.exit(1)
