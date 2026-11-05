import { build } from 'esbuild';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
await mkdir(path.join(root, 'build'), { recursive: true });
const options = {
  absWorkingDir: root, bundle: true, platform: 'browser', target: 'es2019',
  format: 'iife', legalComments: 'inline', charset: 'utf8',
};
await build({ ...options, entryPoints: ['phone/sender-entry.js'], outfile: 'build/plugin.js' });
await build({ ...options, entryPoints: ['phone/core.js'], outfile: 'build/core.test-bundle.js', globalName: 'RingDotCore' });
console.log('Built the Pebble plugin and isolated test bundle.');
