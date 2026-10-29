/** @type {import('tailwindcss').Config} */
// 색상 토큰은 동의과학대학교 홈페이지(dit.ac.kr)의 레드·네이비·스카이 계열을 참고했다.
// 공식 CI 사용권은 미결정(OPEN-008)이므로 '참고 색감'으로만 사용한다.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#fdf2f2',
          100: '#fbe1e0',
          200: '#f6bdbc',
          300: '#f08e8c',
          400: '#ee302e',
          500: '#d8221f',
          600: '#c41816',
          700: '#990c0a',
          800: '#6f0a08',
          900: '#311010',
        },
        navy: {
          50: '#f1f4f8',
          100: '#dde4ee',
          200: '#b9c6d9',
          300: '#8ba0bf',
          400: '#5a7499',
          500: '#3b5679',
          600: '#274160',
          700: '#1a3a5f',
          800: '#1b2740',
          900: '#1a2a3e',
        },
        sky: { 500: '#06a9dc', 100: '#e0f5fc' },
        accent: { 500: '#f98e37', 100: '#fef0e3' },
      },
      fontFamily: {
        sans: ['Pretendard', 'Noto Sans KR', 'Apple SD Gothic Neo', 'Malgun Gothic', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
