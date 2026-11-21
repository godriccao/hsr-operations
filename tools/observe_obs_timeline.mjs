import { existsSync } from 'node:fs';
import { realpath, rename, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { performance } from 'node:perf_hooks';
import { setTimeout as delay } from 'node:timers/promises';
import { openObsFrames } from './obs_frames.mjs';

const folder = resolve(process.argv[2] ?? '');
const requestedTimes = process.argv.slice(3);
const captureTimes = requestedTimes.length ? requestedTimes.map(Number) : [1000, 3000, 6000, 9000, 12000, 16000];
if (captureTimes.length > 24 || captureTimes.some((ms, index) =>
  !Number.isInteger(ms) || ms <= (captureTimes[index - 1] ?? 0) || ms > 16000)) {
  throw new Error('Provide up to 24 increasing capture offsets in milliseconds, from 1 to 16000');
}
const [tempPath, actualFolder] = await Promise.all([realpath(tmpdir()), realpath(folder)]);
if (dirname(actualFolder).toLowerCase() !== tempPath.toLowerCase()
  || !/^hsr-obs-timeline-[a-z0-9-]+$/i.test(basename(actualFolder))) {
  throw new Error('Use a new hsr-obs-timeline-* directory directly under TEMP');
}

const startFile = join(folder, 'start');
const cancelFile = join(folder, 'cancel');
const method = 'OBS Virtual Camera → persistent FFmpeg dshow → next JPEG (960×540)';
const readyFile = join(folder, 'ready.json');
const doneFile = join(folder, 'done.json');
if ([startFile, cancelFile, readyFile, doneFile].some(existsSync)) {
  throw new Error('The observation directory is already in use');
}
await writeFile(join(folder, 'observer.lock'), String(process.pid), { flag: 'wx' });

async function publish(path, data) {
  const temporary = path + '.tmp';
  await writeFile(temporary, JSON.stringify(data, null, 2) + '\n', { flag: 'wx' });
  await rename(temporary, path);
}

const captures = [];
const stream = openObsFrames();
let status = 'complete';
let error;
let startedEpochMs;
try {
  const warm = await stream.nextFrame({ timeoutMs: 8000 });
  await publish(readyFile, { pid: process.pid, method, readyAt: new Date().toISOString(), warmSequence: warm.sequence });
  const deadline = performance.now() + 90000;
  while (!existsSync(startFile)) {
    if (existsSync(cancelFile)) throw new Error('Cancelled before start');
    if (performance.now() >= deadline) throw new Error('No start marker received within 90s');
    await delay(15);
  }
  const started = performance.now();
  startedEpochMs = performance.timeOrigin + started;
  for (const targetMs of captureTimes) {
    const due = started + targetMs;
    while (performance.now() < due) {
      if (existsSync(cancelFile)) throw new Error('Cancelled');
      await delay(Math.min(50, Math.max(1, due - performance.now())));
    }
    const frame = await stream.nextFrame({ timeoutMs: 1200 });
    const name = requestedTimes.length
      ? `t${String(targetMs).padStart(5, '0')}ms.jpg`
      : `t${String(targetMs / 1000).padStart(2, '0')}s.jpg`;
    await writeFile(join(folder, name), frame.bytes, { flag: 'wx' });
    captures.push({ name, targetMs, receivedMs: Math.round(frame.receivedAt - started), sequence: frame.sequence });
  }
} catch (cause) {
  status = 'stopped';
  error = cause.message;
  process.exitCode = 1;
} finally {
  stream.close();
  await publish(doneFile, { status, method, startedEpochMs, captures, error, finishedAt: new Date().toISOString() });
}
