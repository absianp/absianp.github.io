import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://absianp.github.io',
  base: '/',
  markdown: {
    syntaxHighlight: 'shiki',
    shikiConfig: {
      theme: 'github-dark',
      wrap: true,
    },
  },
});
