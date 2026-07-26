import type { Metadata } from "next";
import { headers } from "next/headers";
import "@livekit/components-styles";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const incoming = await headers();
  const host =
    incoming.get("x-forwarded-host") ??
    incoming.get("host") ??
    "localhost:3000";
  const protocol =
    incoming.get("x-forwarded-proto") ??
    (host.startsWith("localhost") ? "http" : "https");
  const baseUrl = new URL(`${protocol}://${host}`);
  const description =
    "A Mandarin voice tutor that turns your Pleco flashcards into real conversation.";
  const imageUrl = new URL("/og.png", baseUrl).toString();

  return {
    metadataBase: baseUrl,
    title: "Plecoach — 把词汇说出来",
    description,
    icons: {
      icon: "/favicon.png",
      shortcut: "/favicon.png",
    },
    openGraph: {
      title: "Plecoach — 把词汇说出来",
      description,
      type: "website",
      url: baseUrl,
      images: [{ url: imageUrl, width: 1731, height: 909, alt: "Plecoach" }],
    },
    twitter: {
      card: "summary_large_image",
      title: "Plecoach — 把词汇说出来",
      description,
      images: [imageUrl],
    },
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
