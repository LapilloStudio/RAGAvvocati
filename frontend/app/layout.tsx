import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RAGAvvocati",
  description: "Assistente documentale sicuro per studi legali e commercialisti",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="it">
      <body>{children}</body>
    </html>
  );
}
