import { sveltekit } from '@sveltejs/kit/vite';
import { SvelteKitPWA } from '@vite-pwa/sveltekit';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [
    sveltekit(),
    SvelteKitPWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'smistress',
        short_name: 'smistress',
        display: 'standalone',
        background_color: '#000000',
        theme_color: '#000000'
      }
    })
  ]
});
