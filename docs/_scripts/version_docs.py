#!/usr/bin/env python3
"""Record successful documentation builds and archive immutable releases."""
import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile


def read_version(root):
    version = (root / '.version').read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', version):
        raise ValueError('Invalid or empty docs/.version')
    return version


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def source_files(root):
    excluded = {'html', 'pdf', '_build', 'versions', '__pycache__', '.venv', '.git'}
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if any(part in excluded for part in relative.parts):
            continue
        if path.is_file() and '.bak' not in path.name:
            yield path


def source_digest(root):
    digest = hashlib.sha256()
    for path in source_files(root):
        digest.update(path.relative_to(root).as_posix().encode('utf-8') + b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def check_products(root, kind):
    if kind == 'html':
        products = [root / 'html/index.html']
        for guide in ('user', 'developer'):
            products.append(root / 'html' / guide / 'index.html')
            products.extend(root / 'html' / p.relative_to(root).with_suffix('.html')
                            for p in (root / guide).rglob('*.rst'))
    else:
        products = [root / 'pdf/user/route-ovs-user.pdf', root / 'pdf/developer/route-ovs-dev.pdf']
    for path in products:
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError('Missing or empty build output: ' + str(path))


def write_version_config(html_root, version, archived=False):
    static = html_root / '_static'
    static.mkdir(exist_ok=True)
    config = {'version': version, 'archived': archived,
              'archiveBase': '../../' if archived else '../versions/'}
    (static / 'version-config.js').write_text(
        'window.ROUTE_OVS_DOC_VERSION = ' + json.dumps(config) + ';\n', encoding='utf-8')


def record_build(root, kind):
    check_products(root, kind)
    if kind == 'html':
        write_version_config(root / 'html', read_version(root))
    write_json(root / kind / '.build-info.json', {
        'version': read_version(root), 'source_sha256': source_digest(root),
        'built_at': timestamp(), 'format': kind,
    })


def check_new_version(root):
    version = read_version(root)
    target = root / 'versions' / version
    if target.exists():
        raise ValueError('Version already archived (will not overwrite): ' + version)
    return version, target


def validate_builds(root, version):
    expected_digest = source_digest(root)
    builds = {}
    for kind in ('html', 'pdf'):
        check_products(root, kind)
        path = root / kind / '.build-info.json'
        if not path.is_file():
            raise ValueError('Build metadata missing; run make all: ' + str(path))
        info = json.loads(path.read_text(encoding='utf-8'))
        if info.get('version') != version or info.get('source_sha256') != expected_digest:
            raise ValueError(kind + ' is from another version or older sources; run make all')
        builds[kind] = info
    return builds


def list_records(root):
    records = []
    for path in sorted((root / 'versions').glob('*/manifest.json')):
        info = json.loads(path.read_text(encoding='utf-8'))
        if info.get('version') != path.parent.name:
            raise ValueError('Archive metadata does not match directory: ' + str(path))
        records.append(info)
    return records


def write_index(root):
    rows = []
    for info in list_records(root):
        version = html.escape(info['version'], quote=True)
        date = html.escape(info['archived_at'])
        rows.append('<tr><td>' + version + '</td><td>' + date + '</td><td>'
                    + '<a href="' + version + '/html/index.html">HTML</a> | '
                    + '<a href="' + version + '/pdf/user/route-ovs-user.pdf">User PDF</a> | '
                    + '<a href="' + version + '/pdf/developer/route-ovs-dev.pdf">Developer PDF</a>'
                    + '</td></tr>')
    content = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
               '<title>文档版本归档</title><h1>文档版本归档</h1>'
               '<table><tr><th>版本</th><th>归档时间（UTC）</th><th>文档</th></tr>'
               + ''.join(rows) + '</table></html>')
    catalog = [{'version': info['version'], 'archived_at': info['archived_at'],
                'pages': info['html_pages']} for info in list_records(root)]
    catalog_temp = root / 'versions/.catalog.tmp'
    catalog_temp.write_text('window.ROUTE_OVS_DOC_VERSIONS = ' +
                            json.dumps(catalog, ensure_ascii=False) + ';\n', encoding='utf-8')
    catalog_temp.replace(root / 'versions/catalog.js')
    temporary = root / 'versions/.index.tmp'
    temporary.write_text(content, encoding='utf-8')
    temporary.replace(root / 'versions/index.html')


def archive_version(root):
    version, target = check_new_version(root)
    builds = validate_builds(root, version)
    target.parent.mkdir(exist_ok=True)
    # A lock prevents two processes from publishing the same version concurrently.
    lock = target.parent / ('.' + version + '.lock')
    lock.mkdir()
    try:
        with tempfile.TemporaryDirectory(prefix='.archive-', dir=target.parent) as temp:
            stage = Path(temp) / version
            stage.mkdir()
            for kind in ('html', 'pdf'):
                shutil.copytree(root / kind, stage / kind,
                                ignore=shutil.ignore_patterns('.doctrees', '__pycache__'))
            write_version_config(stage / 'html', version, archived=True)
            for source in source_files(root):
                dest = stage / 'source' / source.relative_to(root)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
            (stage / '.version').write_text(version + '\n', encoding='utf-8')
            hashes = {p.relative_to(stage).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sorted(stage.rglob('*')) if p.is_file()}
            write_json(stage / 'manifest.json', {
                'version': version, 'archived_at': timestamp(), 'builds': builds,
                'files_sha256': hashes,
                'html_pages': [p.relative_to(stage / 'html').as_posix()
                               for p in sorted((stage / 'html').rglob('*.html'))],
            })
            check_new_version(root)
            stage.rename(target)
        write_index(root)
    finally:
        lock.rmdir()
    print('Archived: ' + str(target))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('record-html', 'record-pdf', 'check', 'archive', 'list'))
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.action.startswith('record-'):
            record_build(root, args.action[7:])
        elif args.action == 'check':
            check_new_version(root)
        elif args.action == 'archive':
            archive_version(root)
        else:
            records = list_records(root)
            if not records:
                print('No archived documentation versions.')
            for info in records:
                print(info['version'] + '\t' + info['archived_at'])
    except (OSError, ValueError) as error:
        print('error: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
