/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'Noto Sans SC', 'Microsoft YaHei', 'sans-serif'],
      },
      colors: {
        brand: {
          50: '#EFF6FF',
          100: '#DBEAFE',
          500: '#3B82F6',
          600: '#2563EB',
          700: '#1D4ED8',
          800: '#1E40AF',
          900: '#1E3A8A',
        },
      },
      keyframes: {
        fadeInUp: {
          from: { opacity: '0', transform: 'translateY(16px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        breathe: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.78' },
        },
        spinSlow: {
          to: { transform: 'rotate(360deg)' },
        },
        slideInRight: {
          from: { transform: 'translateX(100%)' },
          to: { transform: 'translateX(0)' },
        },
        slideOutRight: {
          from: { transform: 'translateX(0)' },
          to: { transform: 'translateX(100%)' },
        },
        fadeIn: {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        fadeOut: {
          from: { opacity: '1' },
          to: { opacity: '0' },
        },
      },
      animation: {
        'fade-in-up': 'fadeInUp 0.45s ease-out both',
        'slide-in-right': 'slideInRight 0.3s ease-out forwards',
        'slide-out-right': 'slideOutRight 0.3s ease-out forwards',
        'fade-in': 'fadeIn 0.3s ease-out forwards',
        'fade-out': 'fadeOut 0.3s ease-out forwards',
        breathe: 'breathe 2.6s ease-in-out infinite',
        'spin-slow': 'spinSlow 1.1s linear infinite',
      },
      animationDelay: {
        'd1': '0.05s',
        'd2': '0.1s',
        'd3': '0.15s',
        'd4': '0.2s',
        'd5': '0.25s',
      },
    },
  },
  plugins: [],
};
