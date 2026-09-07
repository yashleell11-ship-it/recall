import type { Metadata, Viewport } from "next";
import { AppShell } from "@/components/AppShell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Recall",
  description: "Spaced repetition over your own course material.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#faf9f6" },
    { media: "(prefers-color-scheme: dark)", color: "#060810" },
  ],
};

/**
 * Applied before first paint so a stored preference never flashes the other
 * palette — or the other skin. Theme: `system` deliberately writes no
 * attribute, leaving the CSS media query in charge. Skin: the server already
 * renders data-skin="phosphor" (the default), so only a stored non-default
 * actually changes anything here.
 */
const THEME_BOOTSTRAP = `(function(){try{var m=localStorage.getItem("recall.theme");if(m==="light"||m==="dark"){document.documentElement.setAttribute("data-theme",m);}var s=localStorage.getItem("recall.skin");if(s==="phosphor"||s==="ember"||s==="github"){document.documentElement.setAttribute("data-skin",s);}}catch(e){}})();`;

/**
 * Phosphor's three voices, loaded as a plain stylesheet link (deliberately
 * not next/font: simple, CSP-friendly, display=swap). Newsreader carries
 * knowledge text, Inter the interface, JetBrains Mono the telemetry. Ember
 * remains on its system stacks and never touches Newsreader.
 */
const FONTS_HREF =
  "https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400;1,6..72,500&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap";

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className="h-full"
      data-skin="phosphor"
      suppressHydrationWarning
    >
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link rel="stylesheet" href={FONTS_HREF} />
      </head>
      <body className="min-h-full">
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
