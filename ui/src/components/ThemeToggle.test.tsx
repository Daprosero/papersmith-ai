import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ThemeToggle } from './ThemeToggle';

describe('ThemeToggle', () => {
  it('names the theme it will switch to, not the current one', () => {
    render(<ThemeToggle theme="light" onToggle={() => {}} />);
    expect(screen.getByRole('button', { name: /switch to the dark theme/i })).toBeInTheDocument();
  });

  it('reads the other way round on the dark theme', () => {
    render(<ThemeToggle theme="dark" onToggle={() => {}} />);
    expect(screen.getByRole('button', { name: /switch to the light theme/i })).toBeInTheDocument();
  });

  it('reports the current theme to assistive tech and to browser checks', () => {
    render(<ThemeToggle theme="dark" onToggle={() => {}} />);
    const button = screen.getByRole('button');
    expect(button).toHaveAttribute('aria-pressed', 'true');
    expect(button).toHaveAttribute('data-theme', 'dark');
  });

  it('calls back once per activation', async () => {
    const onToggle = vi.fn();
    render(<ThemeToggle theme="light" onToggle={onToggle} />);
    await userEvent.click(screen.getByRole('button'));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it('is reachable and operable from the keyboard', async () => {
    const onToggle = vi.fn();
    render(<ThemeToggle theme="light" onToggle={onToggle} />);
    await userEvent.tab();
    expect(screen.getByRole('button')).toHaveFocus();
    await userEvent.keyboard('{Enter}');
    expect(onToggle).toHaveBeenCalledTimes(1);
  });
});
