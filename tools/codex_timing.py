"""Summarize timing metadata from a completed batch in a Codex session log."""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from statistics import median


CUA_CAPTURE_CALLS = {
    "await app.getScreenshot();",
    "await app.getScreenshot(); var cuaFrame=Date.now();",
    "await app.getScreenshot(); cuaFrame=Date.now(); nodeRepl.write(cuaFrame);",
}
BRIDGE_LINE = re.compile(r"(dispatch|ack) (\d{13}) ((?:keys|click)\|[^|]+\|\d+)")


def bridge_receipts(output, start, end):
    dispatches = []
    acknowledgements = 0
    pending = None
    for line in output.splitlines():
        match = BRIDGE_LINE.fullmatch(line.strip())
        if match is None:
            continue
        event, encoded_time, command = match.groups()
        when = int(encoded_time)
        if not start <= when <= end:
            continue
        if event == "dispatch":
            dispatches.append(when)
            pending = (when, command)
        elif pending and command == pending[1] and when >= pending[0]:
            acknowledgements += 1
            pending = None
    return dispatches, acknowledgements


def timestamp(value):
    when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if when.tzinfo is None:
        raise argparse.ArgumentTypeError("Include a time zone, for example +09:00")
    return int(when.timestamp() * 1000)


def events(path, tail_mib):
    with path.open("rb") as log:
        offset = max(0, path.stat().st_size - tail_mib * 1024 * 1024)
        if offset:
            log.seek(offset - 1)
            if log.read(1) != b"\n":
                log.readline()
        for line in log:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            payload = entry.get("payload", {})
            if payload.get("type") != "item_completed":
                continue
            start, end = payload.get("started_at_ms"), payload.get("completed_at_ms")
            if not isinstance(start, int) or not isinstance(end, int) or end < start:
                continue
            item = payload.get("item", {})
            tool = item.get("tool")
            if item.get("server") == "cua_repl" and tool == "js":
                args = item.get("arguments") or {}
                result = item.get("result") or {}
                code = args.get("code") if isinstance(args, dict) else None
                if (isinstance(code, str) and code.strip() in CUA_CAPTURE_CALLS
                        and item.get("status") == "completed" and not result.get("isError")):
                    tool = "CuaScreenshot"
            state = None
            if tool == "ControlStatus":
                result = item.get("result") or {}
                state = (result.get("structuredContent") or {}).get("state")
            kind = item.get("type")
            receipts = None
            if kind == "CommandExecution":
                receipts = bridge_receipts(item.get("aggregated_output") or "", start, end)
            yield start, end, kind, tool, state, receipts


def samples(entries):
    frame = None
    first_frame_end = None
    frame_count = 0
    reasoning = []
    checks = []
    for start, end, kind, tool, state, receipts in sorted(entries, key=lambda event: event[0]):
        if kind == "McpToolCall" and tool in {"Screenshot", "CuaScreenshot"}:
            if frame is None:
                first_frame_end = end
                frame_count = 0
            frame_count += 1
            frame = (start, end, tool)
            reasoning = []
            checks = []
        elif frame is not None and start >= frame[1]:
            if kind == "Reasoning" and not checks:
                reasoning.append((start, end))
            elif kind == "McpToolCall" and tool == "ControlStatus":
                checks.append((start, end, state))
            elif kind == "CommandExecution" and checks:
                dispatches, acknowledgements = receipts
                first_dispatch = dispatches[0] if dispatches else None
                first_check = checks[0][0]
                first_ready_end = next((b for _, b, status in checks if status == "ready"), None)
                last_busy_end = max((b for _, b, status in checks if status == "ai"
                                     and (first_ready_end is None or b < first_ready_end)), default=None)
                previous_end = frame[1]
                first_reasoning_start = None
                model_ms = 0
                for a, b in reasoning:
                    a, b = max(a, previous_end), min(b, first_check)
                    if a < b:
                        if first_reasoning_start is None:
                            first_reasoning_start = a
                        model_ms += b - a
                        previous_end = b
                review_ms = first_check - frame[1]
                before_reasoning_ms = None
                after_reasoning_ms = None
                if first_reasoning_start is not None:
                    before_reasoning_ms = first_reasoning_start - frame[1]
                    after_reasoning_ms = first_check - previous_end
                yield {
                    "frame_finished_epoch_ms": frame[1],
                    "first_frame_finished_epoch_ms": first_frame_end,
                    "observation_frames": frame_count,
                    "capture_tool": frame[2],
                    "screenshot_ms": frame[1] - frame[0],
                    "frame_to_first_check_ms": review_ms,
                    "frame_to_first_recorded_reasoning_ms": before_reasoning_ms,
                    "recorded_reasoning_ms": model_ms,
                    "last_recorded_reasoning_to_first_check_ms": after_reasoning_ms,
                    "unattributed_before_check_ms": review_ms - model_ms,
                    "first_check_to_command_start_ms": start - first_check,
                    "frame_to_command_start_ms": start - frame[1],
                    "frame_to_first_bridge_dispatch_ms": (first_dispatch - frame[1]
                                                          if first_dispatch is not None else None),
                    "first_frame_to_first_bridge_dispatch_ms": (
                        first_dispatch - first_frame_end if first_dispatch is not None else None),
                    "command_start_to_first_bridge_dispatch_ms": (first_dispatch - start
                                                                  if first_dispatch is not None else None),
                    "bridge_dispatches": len(dispatches),
                    "bridge_acknowledgements": acknowledgements,
                    "control_queries": len(checks),
                    "last_busy_to_first_ready_ms": (first_ready_end - last_busy_end
                                                    if first_ready_end is not None and last_busy_end is not None else None),
                    "first_ready_to_command_start_ms": (start - first_ready_end
                                                        if first_ready_end is not None else None),
                    "command_ms": end - start,
                }
                frame = None
            elif kind in {"UserMessage", "CommandExecution", "McpToolCall"}:
                frame = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--since", type=timestamp)
    parser.add_argument("--until", type=timestamp)
    parser.add_argument("--tail-mib", type=int, default=16)
    parser.add_argument("--capture", choices=("Screenshot", "CuaScreenshot"))
    parser.add_argument("--bridge-only", action="store_true", help="Keep samples with a logged bridge dispatch.")
    args = parser.parse_args()
    if args.tail_mib <= 0:
        parser.error("--tail-mib must be positive")
    if args.since is not None and args.until is not None and args.until < args.since:
        parser.error("--until is earlier than --since")
    try:
        rows = [sample for sample in samples(events(args.log, args.tail_mib))
                if (args.since is None or sample["frame_finished_epoch_ms"] >= args.since)
                and (args.until is None or sample["frame_finished_epoch_ms"] <= args.until)
                and (args.capture is None or sample["capture_tool"] == args.capture)
                and (not args.bridge_only or sample["bridge_dispatches"])]
    except OSError as error:
        parser.error(str(error))
    fields = list(rows[0]) if rows else []
    if fields:
        fields.remove("frame_finished_epoch_ms")
        fields.remove("first_frame_finished_epoch_ms")
        fields.remove("observation_frames")
        fields.remove("capture_tool")
        fields.remove("control_queries")
        fields.remove("bridge_dispatches")
        fields.remove("bridge_acknowledgements")
    medians = {}
    for field in fields:
        recorded = [row[field] for row in rows if row[field] is not None]
        if recorded:
            medians[field] = median(recorded)
    print(json.dumps({"sample_count": len(rows), "samples": rows, "medians_ms": medians}, indent=2))


if __name__ == "__main__":
    main()
