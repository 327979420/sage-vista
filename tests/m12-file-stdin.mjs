// Test transport only: a regular file has a finite EOF independent of pipe
// closure scheduling. Preserve exact bytes; never pass a shell or change JSON.
import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, openSync, closeSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

export function spawnWithFileInput(executable, args, raw, options) {
  if (!(raw instanceof Uint8Array) || 'input' in options || 'stdio' in options ||
      !Number.isSafeInteger(options.timeout) || options.timeout < 1 || options.timeout > 45000) throw new Error('test_file_input_options_invalid');
  const directory = mkdtempSync(join(tmpdir(), 'm12-fixture-stdin-'));
  let fd;
  try {
    const path = join(directory, 'input');
    writeFileSync(path, raw, { flag: 'wx', mode: 0o600 }); // Writer is closed before spawning.
    fd = openSync(path, 'r');
    return spawnSync(executable, args, { ...options, stdio: [fd, 'pipe', 'pipe'] });
  } finally {
    try { if (fd !== undefined) closeSync(fd); }
    finally { rmSync(directory, { recursive: true, force: true }); }
  }
}
