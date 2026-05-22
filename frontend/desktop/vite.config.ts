import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// BUILD_VERSION: 2026-05-02-v2 (bump this to force cache bust)
const BUILD_VERSION = Date.now()

export default defineConfig({
  base: '/',
  plugins: [react()],
  define: {
    __BUILD_VERSION__: JSON.stringify(BUILD_VERSION),
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: {
      output: {
        entryFileNames: `assets/[name]-[hash]-${BUILD_VERSION}.js`,
        chunkFileNames: `assets/[name]-[hash]-${BUILD_VERSION}.js`,
        assetFileNames: `assets/[name]-[hash]-${BUILD_VERSION}.[ext]`,
        manualChunks: {
          'react-vendor': ['react', 'react-dom'],
          'markdown-vendor': ['react-markdown', 'remark-gfm', 'highlight.js'],
          'ui-vendor': ['lucide-react'],
        },
      },
    },
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8003',
      '/ws': {
        target: 'ws://localhost:8003',
        ws: true,
      },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      '/api': 'http://localhost:8003',
      '/ws': {
        target: 'ws://localhost:8003',
        ws: true,
      },
    },
  },
})
