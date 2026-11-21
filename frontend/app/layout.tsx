import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MedBook",
  description: "Code-switched clinic appointment assistant (Urdu, Roman Urdu, English)",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ur">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Noto+Nastaliq+Urdu:wght@400;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
