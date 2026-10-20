import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');

function loadProductionClientEnv() {
  const file = resolve(repositoryRoot, 'prod.env');
  if (!existsSync(file)) return {};
  const values: Record<string, string> = {};
  for (const line of readFileSync(file, 'utf8').split(/\r?\n/)) {
    const match = line.match(/^\s*(VITE_[A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (!match) continue;
    const [, key, raw] = match;
    try {
      values[key] = raw.startsWith('"') && raw.endsWith('"') ? JSON.parse(raw) as string : raw;
    } catch {
      throw new Error(`Invalid ${key} value in repository prod.env`);
    }
  }
  return values;
}

export default defineConfig(({ mode }) => {
  const env = {
    ...loadEnv(mode, repositoryRoot, ''),
    ...(mode === 'production' ? loadProductionClientEnv() : {}),
    ...Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith('VITE_') || key === 'STRIPE_PUBLISHABLE_KEY')),
  };
  return {
    envDir: repositoryRoot,
    define: {
      'import.meta.env.VITE_AUTH_API_URL': JSON.stringify(env.VITE_AUTH_API_URL || ''),
      'import.meta.env.VITE_CAR_API_URL': JSON.stringify(env.VITE_CAR_API_URL || ''),
      'import.meta.env.VITE_BOOKING_API_URL': JSON.stringify(env.VITE_BOOKING_API_URL || ''),
      'import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY': JSON.stringify(env.VITE_STRIPE_PUBLISHABLE_KEY || env.STRIPE_PUBLISHABLE_KEY || ''),
    },
    plugins: [react()],
    server: {
      proxy: {
        '/api/auth': { target: 'http://127.0.0.1:8000', changeOrigin: true, rewrite: (path) => path.replace(/^\/api\/auth/, '/auth') },
        '/api/cars': { target: 'http://127.0.0.1:8002', changeOrigin: true, rewrite: (path) => path.replace(/^\/api\/cars/, '/vehicles') },
        '/api/bookings': { target: 'http://127.0.0.1:8001', changeOrigin: true, rewrite: (path) => path.replace(/^\/api\/bookings/, '/bookings') },
      },
    },
  };
});
