import { useCallback, useEffect, useState } from 'react';

export const THEME_STORAGE_KEY = 'papersmith.theme';

export type Theme = 'light' | 'dark';

const THEMES: readonly Theme[] = ['light', 'dark'];

function isTheme(value: unknown): value is Theme {
  return typeof value === 'string' && (THEMES as readonly string[]).includes(value);
}

/**
 * The stored choice, or null when absent or unrecognized. A hardened browser
 * profile can make `localStorage` throw on read, which must not keep the
 * dashboard from painting.
 */
function storedTheme(): Theme | null {
  try {
    const value = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isTheme(value) ? value : null;
  } catch {
    return null;
  }
}

function systemTheme(): Theme {
  try {
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

/**
 * Theme ownership for the whole dashboard: an explicit choice wins, the system
 * preference decides the first visit, and `light` is the floor when neither is
 * readable. The value is mirrored onto `<html data-theme>`, which is the only
 * hook the stylesheet and the browser checks look at.
 */
export function useTheme(): { theme: Theme; setTheme: (next: Theme) => void; toggle: () => void } {
  const [theme, setThemeState] = useState<Theme>(() => storedTheme() ?? systemTheme());

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // A denied write costs persistence across reloads, nothing else.
    }
  }, []);

  const toggle = useCallback(() => {
    setThemeState((current) => {
      const next: Theme = current === 'dark' ? 'light' : 'dark';
      try {
        window.localStorage.setItem(THEME_STORAGE_KEY, next);
      } catch {
        // See above.
      }
      return next;
    });
  }, []);

  return { theme, setTheme, toggle };
}
