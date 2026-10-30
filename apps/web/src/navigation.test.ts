import { describe, expect, it } from 'vitest';
import { hiddenPaths, isHiddenPath, navigation, normalizePath, visibleNavigation } from './navigation';

describe('release navigation visibility', () => {
  it('keeps all 12 original records but exposes exactly 8 visible menus', () => {
    expect(navigation).toHaveLength(12);
    expect(visibleNavigation.map(item => item.id)).toEqual(['home', 'login', 'discovery', 'community', 'recruitments', 'opportunities', 'information', 'ai']);
  });

  it('treats hidden direct paths, including a trailing slash, as hidden', () => {
    expect(hiddenPaths).toEqual(['/app/academic', '/app/classrooms', '/app/department', '/app/support']);
    for (const path of hiddenPaths) {
      expect(isHiddenPath(path)).toBe(true);
      expect(isHiddenPath(`${path}/`)).toBe(true);
    }
    for (const item of visibleNavigation) expect(isHiddenPath(item.path)).toBe(false);
    expect(isHiddenPath('/app/unknown')).toBe(false);
  });

  it('normalizes trailing slashes and the empty path', () => {
    expect(normalizePath('/app/')).toBe('/app');
    expect(normalizePath('/')).toBe('/app');
    expect(normalizePath('/app/search/')).toBe('/app/search');
  });
});
