import type { Config } from 'tailwindcss';

/**
 * Direction 1 — "Krishi Sahayak" design system.
 *
 * Color naming convention:
 *   leaf-*    — primary brand green (deep, institutional)
 *   saffron-* — accent (India institutional palette pair)
 *   soil-*    — warm neutrals for text and surfaces
 *   ink-*     — pure neutrals for high-contrast text / borders
 *
 * Numbered scales follow Tailwind conventions (50 lightest → 950 darkest).
 * Pick from this palette FIRST; reach for arbitrary hex codes only when
 * the design system genuinely doesn't have a slot for what you need.
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        leaf: {
          50: '#F1F8F1',
          100: '#DCEEDC',
          200: '#B7DCB6',
          300: '#8AC489',
          400: '#5EAA5E',
          500: '#3FA64A',
          600: '#2E7D32',
          700: '#1F5C25',
          800: '#15431B',
          900: '#0C2A12',
          950: '#061608',
        },
        saffron: {
          50: '#FFF8EC',
          100: '#FFE9C2',
          200: '#FFD08A',
          300: '#FFB347',
          400: '#FFA000',
          500: '#E08900',
          600: '#B86E00',
          700: '#8C5400',
          800: '#5E3800',
          900: '#2F1C00',
        },
        soil: {
          50: '#FAF8F4',
          100: '#F0EAE0',
          200: '#DCD0BC',
          300: '#B89E76',
          500: '#7A6543',
          700: '#4A3C28',
          900: '#221B11',
        },
        ink: {
          50: '#F9FAF9',
          100: '#F1F3F1',
          200: '#E1E5E1',
          300: '#C3CAC4',
          400: '#8E9890',
          500: '#5F6B61',
          600: '#414B43',
          700: '#2C342E',
          800: '#1A1F1B',
          900: '#0E120F',
        },
        // Semantic aliases (used by status chips, banners, etc.).
        success: {
          DEFAULT: '#2E7D32',
          soft: '#DCEEDC',
        },
        warning: {
          DEFAULT: '#B86E00',
          soft: '#FFE9C2',
        },
        danger: {
          DEFAULT: '#C62828',
          soft: '#FCE4E4',
        },
        info: {
          DEFAULT: '#1565C0',
          soft: '#DCEAF7',
        },
      },
      fontFamily: {
        // Display = headings, hero text, big numbers.
        // Sans   = body, UI labels, everything else.
        display: ['Poppins', 'Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        // For Devanagari / Tamil / Bengali / etc. — the system falls back
        // to Noto Sans via google-fonts in index.html.
      },
      fontSize: {
        // Slightly tighter scale than Tailwind defaults — gives screens
        // a more polished, less "blog post" rhythm.
        '2xs': ['0.6875rem', { lineHeight: '0.875rem' }],
        xs: ['0.75rem', { lineHeight: '1rem' }],
        sm: ['0.8125rem', { lineHeight: '1.125rem' }],
        base: ['0.9375rem', { lineHeight: '1.375rem' }],
        lg: ['1.0625rem', { lineHeight: '1.5rem' }],
        xl: ['1.25rem', { lineHeight: '1.75rem' }],
        '2xl': ['1.5rem', { lineHeight: '2rem' }],
        '3xl': ['1.875rem', { lineHeight: '2.25rem' }],
        '4xl': ['2.25rem', { lineHeight: '2.5rem' }],
      },
      borderRadius: {
        // Soft, friendly shapes — never sharp 90° corners.
        sm: '0.375rem',
        DEFAULT: '0.5rem',
        md: '0.625rem',
        lg: '0.875rem',
        xl: '1.125rem',
        '2xl': '1.5rem',
        '3xl': '2rem',
      },
      boxShadow: {
        // Layered shadows for depth — used sparingly. The "card" shadow
        // is whispery; "hover" is a touch more lifted; "elev" is for
        // modals / sheets / floating action buttons.
        card: '0 1px 2px 0 rgb(0 0 0 / 0.04), 0 1px 3px 0 rgb(0 0 0 / 0.03)',
        hover: '0 4px 12px -2px rgb(0 0 0 / 0.06), 0 2px 6px -1px rgb(0 0 0 / 0.04)',
        elev: '0 12px 32px -6px rgb(0 0 0 / 0.12), 0 4px 12px -2px rgb(0 0 0 / 0.06)',
        fab: '0 8px 20px -4px rgb(46 125 50 / 0.4), 0 4px 8px -2px rgb(46 125 50 / 0.2)',
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'slide-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'scale-in': {
          '0%': { opacity: '0', transform: 'scale(0.96)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        'pulse-ring': {
          '0%': { transform: 'scale(0.95)', opacity: '0.6' },
          '70%': { transform: 'scale(1.15)', opacity: '0' },
          '100%': { transform: 'scale(0.95)', opacity: '0' },
        },
      },
      animation: {
        'fade-in': 'fade-in 200ms ease-out',
        'slide-up': 'slide-up 300ms cubic-bezier(0.16, 1, 0.3, 1)',
        'scale-in': 'scale-in 200ms cubic-bezier(0.16, 1, 0.3, 1)',
        shimmer: 'shimmer 1.5s ease-in-out infinite',
        'pulse-ring': 'pulse-ring 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
} satisfies Config;
