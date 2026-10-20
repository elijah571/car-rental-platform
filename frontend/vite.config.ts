import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '..', '');
  return {
    envDir: '..',
    define: {
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
