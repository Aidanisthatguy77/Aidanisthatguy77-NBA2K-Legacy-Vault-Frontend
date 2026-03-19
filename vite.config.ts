@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700;900&family=Manrope:wght@400;500;700&display=swap');

@import "tailwindcss";
@import "tw-animate-css";

@custom-variant dark (&:is(.dark *));

@theme inline {
  --font-sans: 'Manrope', sans-serif;
  --color-background: hsl(var(--background));
  --color-foreground: hsl(var(--foreground));
  --color-border: hsl(var(--border));
  --color-input: hsl(var(--input));
  --color-ring: hsl(var(--ring));
  --color-card: hsl(var(--card));
  --color-card-foreground: hsl(var(--card-foreground));
  --color-primary: hsl(var(--primary));
  --color-primary-foreground: hsl(var(--primary-foreground));
  --color-secondary: hsl(var(--secondary));
  --color-secondary-foreground: hsl(var(--secondary-foreground));
  --color-muted: hsl(var(--muted));
  --color-muted-foreground: hsl(var(--muted-foreground));
  --color-accent: hsl(var(--accent));
  --color-accent-foreground: hsl(var(--accent-foreground));
  --color-destructive: hsl(var(--destructive));
  --color-destructive-foreground: hsl(var(--destructive-foreground));
  --radius-sm: calc(var(--radius) - 4px);
  --radius-md: calc(var(--radius) - 2px);
  --radius-lg: var(--radius);
}

:root {
  --background: 0 0% 0%;
  --foreground: 0 0% 100%;
  --card: 240 3.7% 5%;
  --card-foreground: 0 0% 100%;
  --border: 240 3.7% 15%;
  --input: 240 3.7% 15%;
  --ring: 0 84% 40%;
  --primary: 0 84% 40%;
  --primary-foreground: 0 0% 100%;
  --secondary: 240 3.7% 10%;
  --secondary-foreground: 0 0% 100%;
  --muted: 240 3.7% 12%;
  --muted-foreground: 240 5% 65%;
  --accent: 0 84% 40%;
  --accent-foreground: 0 0% 100%;
  --destructive: 0 84% 60%;
  --destructive-foreground: 0 0% 100%;
  --radius: 0.375rem;
}

@layer base {
  * {
    @apply border-border;
    box-sizing: border-box;
  }
  body {
    @apply bg-background text-foreground;
    font-family: 'Manrope', -apple-system, BlinkMacSystemFont, sans-serif;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }
  html {
    scroll-behavior: smooth;
  }
}

.font-heading {
  font-family: 'Barlow Condensed', sans-serif;
}

.btn-primary {
  background: #C8102E;
  color: white;
  font-family: 'Barlow Condensed', sans-serif;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  transition: background 0.2s;
}
.btn-primary:hover {
  background: #9e0c24;
}

.underline-red {
  text-decoration: underline;
  text-decoration-color: #C8102E;
  text-underline-offset: 4px;
}

.red-glow {
  text-shadow: 0 0 20px rgba(200, 16, 46, 0.5);
}

.court-pattern {
  background-color: #000;
  background-image: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 40px,
    rgba(255,255,255,0.02) 40px,
    rgba(255,255,255,0.02) 41px
  ), repeating-linear-gradient(
    90deg,
    transparent,
    transparent 40px,
    rgba(255,255,255,0.02) 40px,
    rgba(255,255,255,0.02) 41px
  );
}

.vault-door {
  position: relative;
  width: 280px;
  height: 280px;
  border-radius: 50%;
  border: 4px solid #C8102E;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #09090B 0%, #000000 100%);
}
.vault-door::before {
  content: '';
  position: absolute;
  width: 260px;
  height: 260px;
  border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.1);
}
.vault-door::after {
  content: '';
  position: absolute;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  border: 3px solid #C8102E;
  background: radial-gradient(circle, #1a1a1a 0%, #000 100%);
}

@media (max-width: 768px) {
  .vault-door { width: 200px; height: 200px; }
  .vault-door::before { width: 180px; height: 180px; }
  .vault-door::after { width: 60px; height: 60px; }
}

.vault-pulse {
  animation: vault-pulse 3s ease-in-out infinite;
}
@keyframes vault-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(200,16,46,0.4); }
  50% { box-shadow: 0 0 0 20px rgba(200,16,46,0); }
}

.comment-item {
  background: #09090B;
  border: 1px solid rgba(255,255,255,0.1);
  padding: 1rem;
  margin-bottom: 1rem;
  transition: border-color 0.3s;
  border-radius: 0.375rem;
}
.comment-item:hover { border-color: rgba(200,16,46,0.3); }

.reply-item {
  margin-left: 2rem;
  border-left: 2px solid #C8102E;
  padding-left: 1rem;
}

.share-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: transparent;
  border: 1px solid rgba(255,255,255,0.2);
  color: white;
  cursor: pointer;
  transition: all 0.3s;
}
.share-btn:hover {
  border-color: #C8102E;
  background: rgba(200,16,46,0.1);
  transform: scale(1.1);
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid rgba(255,255,255,0.1);
  border-top-color: #C8102E;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.animate-fade-in-up {
  animation: fadeInUp 0.5s ease-out forwards;
}
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.hero-section {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  position: relative;
  overflow: hidden;
}

::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: #000; }
::-webkit-scrollbar-thumb { background: #C8102E; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #9e0c24; }
