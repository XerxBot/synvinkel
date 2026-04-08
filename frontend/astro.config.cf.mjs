/**
 * Astro-konfiguration för Cloudflare Pages.
 * Bygg med: npm run build:cf
 */
import { defineConfig } from 'astro/config';
import cloudflare from '@astrojs/cloudflare';
import react from '@astrojs/react';
import tailwind from '@astrojs/tailwind';

export default defineConfig({
  output: 'server',
  adapter: cloudflare({ mode: 'directory' }),
  integrations: [react(), tailwind()],
});
