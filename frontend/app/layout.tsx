import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@fontsource/space-grotesk/500.css";
import "@fontsource/space-grotesk/600.css";
import "@fontsource/space-grotesk/700.css";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";

import { AuthProvider } from "@/lib/auth/auth-context";
import { OrgProvider } from "@/lib/auth/org-context";
import { QueryProvider } from "@/lib/query-provider";

import "./globals.css";

export const metadata: Metadata = {
  title: "Enterprise AI Knowledge & Workflow Platform",
  description: "Document intelligence, RAG, and agentic workflows for organizations.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-paper text-ink-900 font-body antialiased">
        <QueryProvider>
          <AuthProvider>
            <OrgProvider>{children}</OrgProvider>
          </AuthProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
