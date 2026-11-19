import { spawn } from 'node:child_process';
import { EventEmitter } from 'node:events';
import { performance } from 'node:perf_hooks';

const jpegStart = Buffer.from([0xff, 0xd8]);
const jpegEnd = Buffer.from([0xff, 0xd9]);

// OBS must already be publishing the game-only scene through its virtual camera.
export function openObsFrames() {
  const args = [
    '-hide_banner', '-nostdin', '-loglevel', 'error',
    '-f', 'dshow', '-i', 'video=OBS Virtual Camera', '-an',
    '-vf', 'scale=960:540', '-c:v', 'mjpeg', '-q:v', '4', '-threads:v', '1',
    '-f', 'image2pipe', 'pipe:1',
  ];
  const startedAt = performance.now();
  const reader = spawn('ffmpeg', args, {
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const events = new EventEmitter();
  let latest = null;
  let pending = Buffer.alloc(0);
  let stderr = '';
  let closed = false;
  let failure;

  reader.stderr.on('data', chunk => {
    stderr = (stderr + chunk.toString()).slice(-2048);
  });
  reader.on('error', error => {
    failure = error;
  });
  reader.once('close', (code, signal) => {
    failure ??= new Error(stderr.trim() || `OBS frame reader closed (${code ?? signal})`);
    events.emit('closed');
  });
  reader.stdout.on('data', chunk => {
    pending = pending.length ? Buffer.concat([pending, chunk]) : chunk;
    while (pending.length > 1) {
      const start = pending.indexOf(jpegStart);
      if (start < 0) {
        pending = pending.subarray(pending.length - 1);
        return;
      }
      const end = pending.indexOf(jpegEnd, start + jpegStart.length);
      if (end < 0) {
        pending = pending.subarray(start);
        if (pending.length > 4 * 1024 * 1024) pending = Buffer.alloc(0);
        return;
      }
      latest = {
        bytes: Buffer.from(pending.subarray(start, end + jpegEnd.length)),
        receivedAt: performance.now(),
        sequence: (latest?.sequence ?? 0) + 1,
      };
      pending = pending.subarray(end + jpegEnd.length);
      events.emit('frame', latest);
    }
  });

  function nextFrame({ after = latest?.sequence ?? 0, timeoutMs = 1500 } = {}) {
    if (closed || failure) return Promise.reject(failure ?? new Error('OBS frame reader closed'));
    if (latest?.sequence > after) return Promise.resolve(latest);
    return new Promise((resolve, reject) => {
      const cleanup = () => {
        clearTimeout(timeout);
        events.off('frame', onFrame);
        events.off('closed', onClosed);
      };
      const onFrame = frame => {
        if (frame.sequence <= after) return;
        cleanup();
        resolve(frame);
      };
      const onClosed = () => {
        cleanup();
        reject(failure ?? new Error('OBS frame reader closed'));
      };
      const timeout = setTimeout(() => {
        cleanup();
        reject(new Error(`No new OBS JPEG after ${timeoutMs}ms`));
      }, timeoutMs);
      events.on('frame', onFrame);
      events.on('closed', onClosed);
    });
  }

  return {
    startedAt,
    nextFrame,
    close() {
      if (closed) return;
      closed = true;
      latest = null;
      reader.kill();
      events.emit('closed');
    },
  };
}
