/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#101828',
        fog: '#eef2f6',
        cloud: '#f8fafc',
        accent: '#0f766e',
      },
      boxShadow: {
        ambient: '0 20px 60px -30px rgba(15, 23, 42, 0.28)',
        soft: '0 14px 40px -28px rgba(15, 23, 42, 0.24)',
      },
    },
  },
  plugins: [],
};
