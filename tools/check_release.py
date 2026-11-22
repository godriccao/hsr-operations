"""Check the public file contract: local links, text-only allowlist and accidental secrets."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUFFIXES = {'.md', '.py', '.ahk', '.ini', '.txt', '.jsonl', '.yaml', '.yml', '.mjs'}
FORBIDDEN = [r'(?i)(?<![a-z0-9])[a-z]:[/\\]', r'(?i)/' + r'home/[^/\s]+', r'(?i)Users[/\\][^/\\\s]+',
             r'gh[pousr]_[A-Za-z0-9]{20,}', r'github_pat_[A-Za-z0-9_]{20,}',
             r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----',
             r'(?i)\b(?:UID|account_id)\s*[:=]\s*\d{6,}', r'(?i)Bearer\s+[A-Za-z0-9_.-]{20,}']


def files():
    if (ROOT / '.git').exists():
        result = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '-z'], capture_output=True, check=True)
        return [ROOT / p for p in result.stdout.decode().split('\0') if p]
    return [p for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts]


def check():
    errors = []
    paths = files()
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        if (path.suffix not in SUFFIXES
                and path.name not in {'LICENSE', '.gitignore', '.gitattributes'}
                and relative != 'tools/start_obs_timeline.ps1'):
            errors.append(f'unsupported public file: {relative}')
        try:
            text = path.read_text(encoding='utf-8-sig')
        except (ValueError, UnicodeError):
            errors.append(f'non-text file: {relative}')
            continue
        for pattern in FORBIDDEN:
            if re.search(pattern, text):
                errors.append(f'sensitive pattern in {relative}: {pattern}')
        if path.suffix == '.md':
            for target in re.findall(r'\]\(([^\s)]+)\)', text):
                if target.startswith(('https://', 'http://', '#', 'mailto:')):
                    continue
                if not (path.parent / target.split('#')[0]).is_file():
                    errors.append(f'broken link in {relative}: {target}')
    for name in ('LICENSE', 'README.md', 'docs/INSTALL.md', 'docs/EVIDENCE.md',
                 'docs/PERFORMANCE.md', 'skills/hsr-operations/SKILL.md'):
        if not (ROOT / name).is_file():
            errors.append(f'missing required file: {name}')
    return len(paths), errors


if __name__ == '__main__':
    count, errors = check()
    for error in errors:
        print(error)
    print(f'public files={count}; errors={len(errors)}')
    raise SystemExit(bool(errors))
