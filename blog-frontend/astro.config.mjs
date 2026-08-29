import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://yourusername.github.io',
  markdown: {
    syntaxHighlight: 'shiki',
    shikiConfig: {
      theme: 'github-dark',
      wrap: true,
    },
  },
});
