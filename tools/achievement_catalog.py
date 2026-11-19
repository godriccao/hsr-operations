"""Fetch, validate and compare local Chinese achievement catalog snapshots."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_URL = 'https://static.nanoka.cc/manifest.json'
CATALOG_URL = 'https://static.nanoka.cc/hsr/{version}/zh/achievement/achievement.json'
SCHEMA_VERSION = 1
MAX_BYTES = 8 * 1024 * 1024
VERSION_PATTERN = re.compile(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)')
SHA256_PATTERN = re.compile(r'[0-9a-f]{64}')
REQUIRED_SERIES = frozenset(str(i) for i in range(1, 10))
REWARD = {'Low': 5, 'Mid': 10, 'High': 20}
DISPLAY = {'VISIBLE', 'HiddenDesc', 'ShowAfterFinish'}
UNBREAK = re.compile(r'</?unbreak>')


def distinct_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f'invalid JSON number: {value}')


def finite_float(value):
    number = float(value)
    return number if math.isfinite(number) else reject_constant(value)


def parse_json(payload):
    return json.loads(payload.decode('utf-8-sig'), object_pairs_hook=distinct_keys,
                      parse_constant=reject_constant, parse_float=finite_float)


def limited_read(stream):
    payload = stream.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError('catalog payload exceeds 8 MiB')
    return payload


def fetch(url):
    request = Request(url, headers={'User-Agent': 'hsr-operations-achievement-catalog/1',
                                    'Accept': 'application/json'})
    try:
        with urlopen(request, timeout=15) as response:
            if response.geturl() != url:
                raise ValueError('unexpected catalog URL redirect')
            return limited_read(response)
    except HTTPError as exc:
        raise ValueError(f'catalog source returned HTTP {exc.code}: {url}') from exc
    except (URLError, TimeoutError) as exc:
        raise ValueError(f'catalog source unavailable: {url} ({exc})') from exc


def release_version(version):
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise ValueError('expected a formal release version in major.minor form')
    return version


def select_version(payload, requested):
    manifest = parse_json(payload)
    hsr = manifest.get('hsr') if isinstance(manifest, dict) else None
    if not isinstance(hsr, dict):
        raise ValueError('manifest is missing the hsr version section')
    available = hsr.get('available')
    live = release_version(hsr.get('live'))
    if not isinstance(available, list) or live not in available:
        raise ValueError('manifest formal live version is missing from available')
    version = release_version(requested) if requested is not None else live
    if version not in available:
        raise ValueError(f'version {version} is absent from the source manifest')
    return version


def text_field(row, field):
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'catalog is missing a usable {field}')
    return value


def normalize_catalog(payload):
    groups = parse_json(payload)
    if not isinstance(groups, dict) or not REQUIRED_SERIES.issubset(groups):
        raise ValueError('catalog is missing an expected achievement series')
    rows = {}
    for key, series in groups.items():
        if not isinstance(series, dict) or type(series.get('id')) is not int or str(series['id']) != key:
            raise ValueError(f'invalid catalog series: {key}')
        category = text_field(series, 'name')
        entries = series.get('list')
        if not isinstance(entries, list) or not entries:
            raise ValueError(f'catalog series {key} has no achievement list')
        for item in entries:
            if not isinstance(item, dict) or type(item.get('id')) is not int or item['id'] <= 0:
                raise ValueError(f'invalid achievement ID in series {key}')
            identifier = item['id']
            if identifier in rows:
                raise ValueError(f'duplicate achievement ID: {identifier}')
            name = UNBREAK.sub('', text_field(item, 'name'))
            description = text_field(item, 'desc')
            rarity, display = text_field(item, 'rarity'), text_field(item, 'show_type')
            params = item.get('param_list')
            if (not name.strip() or rarity not in REWARD or display not in DISPLAY
                    or not isinstance(params, list) or any(type(p) not in (int, float, str) for p in params)):
                raise ValueError(f'invalid achievement fields for ID {identifier}')
            rows[identifier] = {'id': identifier, 'series_id': series['id'], 'series_name': category,
                                'name': name, 'description': description, 'parameters': params,
                                'rarity': rarity, 'jade': REWARD[rarity], 'show_type': display}
    return [rows[identifier] for identifier in sorted(rows)]


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def make_snapshot(version, payload, source_url, manifest_digest):
    rows = normalize_catalog(payload)
    return {'schema_version': SCHEMA_VERSION, 'version': version, 'language': 'zh',
            'source': {'provider': 'Nanoka', 'url': source_url,
                       'origin': 'download' if source_url else 'local_input',
                       'manifest_url': MANIFEST_URL if manifest_digest else None,
                       'manifest_sha256': manifest_digest, 'sha256': digest(payload),
                       'bytes': len(payload)},
            'captured_at': datetime.now(timezone.utc).isoformat(), 'row_count': len(rows), 'items': rows}


def load_snapshot(path):
    if not path.exists():
        return None
    snapshot = parse_json(path.read_bytes())
    try:
        rows = snapshot['items']
        identifiers = [row['id'] for row in rows]
        valid = (snapshot['schema_version'] == SCHEMA_VERSION and snapshot['language'] == 'zh'
                 and SHA256_PATTERN.fullmatch(snapshot['source']['sha256'])
                 and release_version(snapshot['version']) and snapshot['row_count'] == len(rows)
                 and rows and all(type(i) is int and i > 0 for i in identifiers)
                 and identifiers == sorted(set(identifiers)))
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError('existing local catalog is invalid; it was left in place')
    return snapshot


def difference(previous, current):
    old = {row['id']: row for row in previous['items']} if previous else {}
    new = {row['id']: row for row in current['items']}
    return {'added': sorted(new.keys() - old.keys()), 'removed': sorted(old.keys() - new.keys()),
            'changed': [{'id': i, 'fields': sorted(key for key in old[i].keys() | new[i].keys()
                                                    if old[i].get(key) != new[i].get(key))}
                        for i in sorted(old.keys() & new.keys()) if old[i] != new[i]]}


@contextmanager
def update_lock(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'update.lock').open('a+b') as lock:
        # The operating system releases the advisory lock if the process exits.
        if os.name == 'nt':
            import msvcrt
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def atomic_json(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', dir=path.parent, encoding='utf-8',
                                         newline='\n', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def compare_and_update(directory, snapshot, publish):
    active = directory / 'current.json'
    previous = load_snapshot(active)
    if previous:
        previous_version = tuple(map(int, previous['version'].split('.')))
        incoming_version = tuple(map(int, snapshot['version'].split('.')))
        if incoming_version < previous_version:
            raise ValueError('incoming catalog is older than the active version; use a separate output directory')
    delta = difference(previous, snapshot)
    previous_sha = previous['source']['sha256'] if previous else None
    same = bool(previous and previous['version'] == snapshot['version'] and previous_sha == snapshot['source']['sha256'])
    mode = 'preview'
    if publish and same:
        mode = 'unchanged'
    if publish and not same:
        print(f"Catalog change: {len(delta['added'])} added, {len(delta['changed'])} changed, "
              f"{len(delta['removed'])} removed.", file=sys.stderr, flush=True)
        history = directory / 'versions'
        history.mkdir(exist_ok=True)
        snapshot_path = history / f"{snapshot['version']}-{snapshot['source']['sha256']}.json"
        archived = load_snapshot(snapshot_path)
        if archived is None:
            atomic_json(snapshot_path, snapshot)
        elif (archived['version'] != snapshot['version'] or archived['source']['sha256'] != snapshot['source']['sha256']
              or archived['items'] != snapshot['items']):
            raise ValueError('local archive does not match the incoming snapshot')
        atomic_json(active, snapshot)
        mode = 'saved'
    return {'mode': mode, 'from_version': previous['version'] if previous else None,
            'from_sha256': previous_sha, 'to_version': snapshot['version'],
            'rows': snapshot['row_count'], 'sha256': snapshot['source']['sha256'], **delta}


def load_candidate(args):
    if args.input:
        version = release_version(args.version)
        with args.input.open('rb') as stream:
            payload = limited_read(stream)
        source_url = manifest_digest = None
    else:
        manifest = fetch(MANIFEST_URL)
        version = select_version(manifest, args.version)
        source_url = CATALOG_URL.format(version=version)
        payload = fetch(source_url)
        manifest_digest = digest(manifest)
    snapshot = make_snapshot(version, payload, source_url, manifest_digest)
    if args.expect_count is not None and snapshot['row_count'] != args.expect_count:
        raise ValueError(f"expected {args.expect_count} IDs; received {snapshot['row_count']}")
    return snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'runtime' / 'achievement-catalog')
    parser.add_argument('--version', help='Formal release version; defaults to the source manifest live field')
    parser.add_argument('--input', type=Path, help='Read a local Nanoka payload instead of contacting the source')
    parser.add_argument('--expect-count', type=int, help='Require this many achievement IDs before replacing the cache')
    parser.add_argument('--dry-run', action='store_true', help='Compare without changing the local cache')
    args = parser.parse_args(argv)
    if args.input and not args.version:
        parser.error('--input requires an explicit --version for provenance')
    try:
        if args.dry_run:
            result = compare_and_update(args.output, load_candidate(args), False)
        else:
            with update_lock(args.output):
                result = compare_and_update(args.output, load_candidate(args), True)
        print(json.dumps(result, ensure_ascii=True), flush=True)
    except (ValueError, OSError) as exc:
        print(f'Catalog update failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
