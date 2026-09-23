import type { Config } from "tailwindcss";

/**
 * Semantic colours map onto the captured design-system custom properties in
 * `src/styles/theme.css`. Tailwind 3.4.17 stays in place: these are plain `var()` bindings, not
 * v4 `@theme` tokens, so the compiler and the CSS entry point are unchanged. Components use
 * `bg-card`, `text-muted-foreground` and friends instead of hardcoded slate shades, which is what
 * lets the light/dark themes and the business outcome colours actually reach every surface.
 */
const token = (name: string) => `var(--${name})`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: token("background"),
        foreground: token("foreground"),
        card: { DEFAULT: token("card"), foreground: token("card-foreground") },
        popover: { DEFAULT: token("popover"), foreground: token("popover-foreground") },
        primary: { DEFAULT: token("primary"), foreground: token("primary-foreground") },
        "primary-hover": token("primary-hover"),
        secondary: { DEFAULT: token("secondary"), foreground: token("secondary-foreground") },
        muted: { DEFAULT: token("muted"), foreground: token("muted-foreground") },
        accent: { DEFAULT: token("accent"), foreground: token("accent-foreground") },
        destructive: { DEFAULT: token("destructive") },
        border: token("border"),
        input: token("input"),
        ring: token("ring"),
        warning: token("warning-foreground"),
        link: token("link"),
        sidebar: {
          DEFAULT: token("sidebar"),
          foreground: token("sidebar-foreground"),
          primary: token("sidebar-primary"),
          accent: token("sidebar-accent"),
          border: token("sidebar-border"),
          ring: token("sidebar-ring"),
        },
        // Business outcomes stay separate from primary: blue is not success.
        success: token("state-success"),
        pending: token("state-pending"),
        failure: token("state-failure"),
      },
      borderRadius: {
        lg: token("radius"),
        md: `calc(${token("radius")} - 2px)`,
        sm: `calc(${token("radius")} - 4px)`,
      },
      fontFamily: {
        sans: [token("font-sans")],
        heading: [token("font-heading")],
      },
    },
  },
  plugins: [],
} satisfies Config;
