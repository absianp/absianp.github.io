/**
 * URL Slug and Category Helper Functions for 100% 404-Free GitHub Pages Navigation
 */

export function getCategorySlug(category: string = ''): string {
  const normalized = category.trim().toLowerCase();
  if (normalized.includes('ai') || normalized.includes('생산성') || normalized.includes('productivity')) {
    return 'ai-productivity';
  }
  if (normalized.includes('개발') || normalized.includes('테크') || normalized.includes('dev') || normalized.includes('tech')) {
    return 'tech-dev';
  }
  if (normalized.includes('부업') || normalized.includes('재테크') || normalized.includes('income')) {
    return 'side-income';
  }
  return normalized
    .replace(/&/g, 'and')
    .replace(/[\s\/\\]+/g, '-')
    .replace(/[^\w-]/g, '')
    .replace(/--+/g, '-')
    .replace(/^-+|-+$/g, '') || 'general';
}

export function getCategoryName(slug: string): string {
  const map: Record<string, string> = {
    'ai-productivity': 'AI & 생산성',
    'tech-dev': '개발 & 테크',
    'side-income': '스마트 부업 & 재테크',
    'general': '일반',
  };
  return map[slug] || slug.replace(/-/g, ' ').toUpperCase();
}

export function getTagSlug(tag: string = ''): string {
  return tag
    .trim()
    .toLowerCase()
    .replace(/&/g, 'and')
    .replace(/[\s\/\\]+/g, '-')
    .replace(/[^\w\uAC00-\uD7A3-]/g, '')
    .replace(/--+/g, '-')
    .replace(/^-+|-+$/g, '') || 'tag';
}
