/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        discord: {
          blurple: '#5865F2',
          'blurple-hover': '#4752C4',
          'dark-gray': '#313338',
          'darker-gray': '#2b2d31',
          'darkest-gray': '#1e1f22',
          green: '#248046',
          'green-hover': '#1a6535',
          red: '#da373c',
          'red-hover': '#a92b2f',
          yellow: '#f0b232',
          'text-primary': '#f2f3f5',
          'text-muted': '#949ba4',
          card: '#2b2d31',
          tooltip: '#111214',
        }
      },
      fontFamily: {
        sans: ['Outfit', 'Inter', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
