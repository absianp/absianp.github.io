import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://absianp.github.io',
  base: '/auto-blog',
  markdown: {
    syntaxHighlight: 'shiki',
    shikiConfig: {
      theme: 'github-dark',
      wrap: true,
    },
  },
});
