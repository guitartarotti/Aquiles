import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      '@locales': path.resolve(__dirname, '../locales'),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['tests/components/**/*.component.test.js'],
    setupFiles: ['./tests/components/setup.js'],
    restoreMocks: true,
  },
})
