import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        leaf: {
          50: '#f3faf3',
          100: '#e3f5e1',
          500: '#3fa64a',
          600: '#2f8a39',
          700: '#246e2c',
          900: '#143a17',
        },
        soil: {
          50: '#faf6f0',
          500: '#a07d4e',
          900: '#3f2e15',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config;
