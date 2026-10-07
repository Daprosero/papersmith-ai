import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { THEME_STORAGE_KEY, useTheme } from './useTheme';

/** Replace `matchMedia` with one that answers a fixed dark-scheme preference. */
function stubPrefersDark(prefersDark: boolean): void {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes('prefers-color-scheme: dark') ? prefersDark : false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

describe('useTheme', () => {
  beforeEach(() => {
    window.localStorage.clear();
    delete document.documentElement.dataset.theme;
    stubPrefersDark(false);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('follows the system preference when nothing was chosen yet', () => {
    stubPrefersDark(true);
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('defaults to light when the system has no dark preference', () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('light');
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('prefers a stored choice over the system preference', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light');
    stubPrefersDark(true);
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('light');
  });

  it('writes the chosen theme to the document and to storage', () => {
    const { result } = renderHook(() => useTheme());
    act(() => result.current.toggle());
    expect(result.current.theme).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
  });

  it('toggles back to light', () => {
    const { result } = renderHook(() => useTheme());
    act(() => result.current.toggle());
    act(() => result.current.toggle());
    expect(result.current.theme).toBe('light');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
  });

  it('ignores a corrupt stored value instead of rendering an unknown theme', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'solarized-midnight');
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('light');
  });

  it('survives storage that throws, as in a hardened browser profile', () => {
    const setItem = vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
      throw new Error('denied');
    });
    const { result } = renderHook(() => useTheme());
    expect(() => act(() => result.current.toggle())).not.toThrow();
    expect(result.current.theme).toBe('dark');
    setItem.mockRestore();
  });
});
