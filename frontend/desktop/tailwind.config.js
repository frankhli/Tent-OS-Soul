/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Tent OS 主题设计系统 —— 通过 CSS 变量自动切换 light/dark
        surface: {
          base: 'var(--bg-base)',
          elevated: 'var(--bg-elevated)',
          panel: 'var(--bg-panel)',
          overlay: 'var(--bg-overlay)',
          input: 'var(--bg-input)',
        },
        line: {
          subtle: 'var(--line-subtle)',
          DEFAULT: 'var(--line-default)',
          active: 'var(--line-active)',
        },
        content: {
          primary: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted: 'var(--text-muted)',
          disabled: 'var(--text-disabled)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          hover: 'var(--accent-hover)',
          subtle: 'var(--accent-subtle)',
          border: 'var(--accent-border)',
        },
        tent: {
          50: '#f0fdf4',
          100: '#dcfce7',
          200: '#bbf7d0',
          300: '#86efac',
          400: '#4ade80',
          500: '#22c55e',
          600: '#16a34a',
          700: '#15803d',
          800: '#166534',
          900: '#14532d',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      boxShadow: {
        'elevation-1': '0 1px 3px rgba(0,0,0,0.08), 0 0 0 1px rgba(0,0,0,0.04)',
        'elevation-2': '0 4px 12px rgba(0,0,0,0.10), 0 0 0 1px rgba(0,0,0,0.05)',
        'elevation-1-dark': '0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.03)',
        'elevation-2-dark': '0 4px 12px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.04)',
      },
    },
  },
  plugins: [],
}
