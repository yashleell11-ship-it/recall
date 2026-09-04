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
    { media: "(prefers-color-scheme: dark)", color: "#16151a" },
  ],
};

/**
 * Applied before first paint so a stored preference never flashes the other
 * palette. `system` deliberately writes no attribute, leaving the CSS media
 * query in charge.
 */
const THEME_BOOTSTRAP = `(function(){try{var m=localStorage.getItem("recall.theme");if(m==="light"||m==="dark"){document.documentElement.setAttribute("data-theme",m);}}catch(e){}})();`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <body className="min-h-full">
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
