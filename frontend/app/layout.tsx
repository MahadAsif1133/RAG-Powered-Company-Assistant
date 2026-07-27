import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "KnowledgeAssist — Company Knowledge Assistant",
  description:
    "Instantly answer employee questions about HR policies, SOPs, and onboarding guides using AI-powered document search.",
  keywords: ["HR", "knowledge base", "internal tools", "AI assistant"],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-surface text-white antialiased font-sans">
        {children}
      </body>
    </html>
  );
}
