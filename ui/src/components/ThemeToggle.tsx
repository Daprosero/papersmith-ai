import type { Theme } from '../hooks/useTheme';

interface ThemeToggleProps {
  theme: Theme;
  onToggle: () => void;
}

/**
 * The theme control. Its label names the destination rather than the current
 * state, which is what a reader needs in order to predict what the click does.
 * `data-theme` mirrors the current theme so a browser check can assert the
 * switch without reading the stylesheet.
 */
export function ThemeToggle({ theme, onToggle }: ThemeToggleProps) {
  const next: Theme = theme === 'dark' ? 'light' : 'dark';
  return (
    <button
      type="button"
      className="button button--ghost theme-toggle"
      onClick={onToggle}
      aria-pressed={theme === 'dark'}
      data-theme={theme}
      title={`Switch to the ${next} theme`}
    >
      <span aria-hidden="true" className="theme-toggle__glyph">
        {theme === 'dark' ? '◑' : '◐'}
      </span>
      <span className="theme-toggle__label">Switch to the {next} theme</span>
    </button>
  );
}
