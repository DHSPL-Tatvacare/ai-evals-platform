/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(process.env.npm_package_version),
    __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  },
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
    // Pin one React copy so a mid-session dep re-optimize can't spawn a second
    // instance and null the hook dispatcher ("Invalid hook call").
    dedupe: ['react', 'react-dom'],
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
  },
  server: {
    host: '0.0.0.0',
    // Dev server only: lets local ngrok URLs reach Vite without affecting production builds.
    allowedHosts: ['frontend', '.ngrok-free.app', '.ngrok-free.dev'],
    proxy: {
      '/api': {
        target: process.env.API_PROXY_TARGET || 'http://localhost:8721',
        changeOrigin: true,
      },
      // Local docs parity: /docs is served by the Zudoku dev server (docs
      // container) so it renders at the same origin. Prod serves the built
      // docs via nginx at /docs instead. No changeOrigin — keep the Host as
      // localhost so the docs vite server's anti-DNS-rebinding host check
      // (which blocks the "docs" hostname) lets the request through.
      '/docs': {
        target: process.env.DOCS_PROXY_TARGET || 'http://localhost:5174',
        ws: true,
      },
    },
  },
})
