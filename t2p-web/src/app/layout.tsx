import type { Metadata } from "next";
import "./globals.css";
import ClientWrapper from "./ClientWrapper"; // Add Import

export const metadata: Metadata = {
  title: "Calculus Atelier",
  description: "An adaptive calculus learning and research studio powered by structured generation and agentic review.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      data-scroll-behavior="smooth"
      className="h-full antialiased"
    >
      <body className="min-h-full flex flex-col bg-[#F8FAFC]">
        {/* Provide global user context using ClientWrapper */}
        <ClientWrapper>
          {children}
        </ClientWrapper>
      </body>
    </html>
  );
}
