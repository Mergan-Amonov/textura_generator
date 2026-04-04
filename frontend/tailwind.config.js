/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        surface:  '#111827',
        panel:    '#1f2937',
        border:   '#374151',
        accent:   '#6366f1',
        'accent-hover': '#4f46e5',
      },
    },
  },
  plugins: [],
}
