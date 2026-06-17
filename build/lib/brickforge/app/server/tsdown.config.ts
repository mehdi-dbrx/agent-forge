import { defineConfig } from 'tsdown';

export default defineConfig({
  entry: ['./src/index.ts'],
  format: ['esm'],
  target: 'node22',
  unbundle: false,
  // Explicitly mark what should be external (everything except workspace packages)
  external: [],
  // Force workspace packages to be bundled
  noExternal: [/./],
  dts: false,
});
