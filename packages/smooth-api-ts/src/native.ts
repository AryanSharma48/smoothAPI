import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);

let native: { calculateBackoffNative: (attempt: number, base: number, max: number) => number } | null = null;

try {
  native = require('../../bindings/node');
} catch {
  native = null;
}

export function calculateBackoffWithNative(attempt: number, base: number, max: number): number {
  if (native) {
    return native.calculateBackoffNative(attempt, base, max);
  }
  return Math.min(max, base * (2 ** attempt));
}
