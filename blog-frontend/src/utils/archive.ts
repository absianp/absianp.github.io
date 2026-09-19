import type { CollectionEntry } from 'astro:content';
export const POSTS_PER_PAGE = 18;
export const archivePath = (page: number) => page === 1 ? '/blog/' : `/blog/page/${page}/`;
export const sortPosts = (posts: CollectionEntry<'blog'>[]) => [...posts].sort((a, b) =>
  b.data.pubDate.valueOf() - a.data.pubDate.valueOf() || a.slug.localeCompare(b.slug));
