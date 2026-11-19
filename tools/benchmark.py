"""Validate normalized timing JSONL; report first-operable-frame latency by category."""
import argparse
import json
from pathlib import Path
from statistics import median


def number(value):
    return type(value) in (int, float) and value >= 0 and value < float('inf')


def validate(row):
    frames = row.get('frames_ms')
    if (not isinstance(frames, list) or not frames or not all(map(number, frames))
            or frames != sorted(frames) or row.get('first_frame_ms') != frames[0]):
        raise ValueError('invalid first frame / observation window')
    if row.get('category') not in ('menu', 'movement', 'interaction'):
        raise ValueError('invalid category')
    if not any(row.get('operable') is value for value in (True, False, None)):
        raise ValueError('invalid operable state')
    if not any(row.get('target_hit') is value for value in (True, False, None)):
        raise ValueError('invalid target_hit state')
    events = row.get('events')
    if not isinstance(events, list) or not events:
        raise ValueError('missing receipts')
    pending = None
    previous = frames[-1]
    first_dispatch = None
    count = 0
    for event in events:
        when, command = event.get('t_ms'), event.get('command')
        if not number(when) or when < previous or not isinstance(command, str) or not command:
            raise ValueError('invalid / unordered receipt')
        previous = when
        if event.get('type') == 'dispatch' and pending is None:
            pending = command
            if first_dispatch is None:
                first_dispatch = when
        elif event.get('type') == 'ack' and pending is not None and command == pending:
            pending = None
            count += 1
        else:
            raise ValueError('unmatched or overlapping receipt')
    if pending is not None or first_dispatch != row.get('dispatch_ms'):
        raise ValueError('missing ACK or inconsistent dispatch time')
    return first_dispatch - frames[0], count


def summarize(rows):
    groups = {k: [] for k in ('menu', 'movement', 'interaction')}
    excluded = {'not_operable': 0, 'operability_unknown': 0}
    invalid = []
    acknowledgements = 0
    for index, row in enumerate(rows, 1):
        try:
            latency, paired = validate(row)
        except (ValueError, TypeError, AttributeError) as error:
            invalid.append({'row': index, 'reason': str(error)})
            continue
        if row.get('operable') is not True:
            excluded['not_operable' if row.get('operable') is False else 'operability_unknown'] += 1
            continue
        acknowledgements += paired
        groups[row['category']].append((latency, row.get('target_hit')))

    def metrics(values):
        latencies = [v for v, _ in values]
        verified = [hit for _, hit in values if hit is not None]
        return {'sample_count': len(values), 'median_ms': median(latencies) if values else None,
                'below_3000_ms': sum(v < 3000 for v in latencies),
                'below_5000_ms': sum(v < 5000 for v in latencies),
                'target_hit_count': sum(hit is True for hit in verified),
                'target_verified_count': len(verified), 'target_unverified_count': len(values)-len(verified)}

    return {'overall': metrics([v for values in groups.values() for v in values]),
            'categories': {key: metrics(value) for key, value in groups.items()},
            'paired_acknowledgements': acknowledgements, 'excluded': excluded, 'invalid': invalid}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    args = parser.parse_args()
    try:
        rows = [json.loads(line) for line in args.log.read_text(encoding='utf-8').splitlines() if line.strip()]
        result = summarize(rows)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result['invalid'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
