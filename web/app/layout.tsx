import type { Metadata } from "next";
import { Inter, Archivo } from "next/font/google";
import "./globals.css";

import { Providers } from "./providers";
import { Sidebar } from "@/components/layout/Sidebar";

// Inter — open-source stand-in for Circular (DESIGN.md note on font substitutes).
// Display tiers render at weight 500 with negative tracking at the component level.
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

// Archivo Black — CertQA 워드마크 전용 디스플레이 폰트(본문은 Inter 유지).
const archivo = Archivo({
  variable: "--font-archivo",
  subsets: ["latin"],
  weight: ["900"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "CertQA — 자격검정 문항 검수",
  description:
    "자격검정 문항지의 오타·맞춤법·법령 오류 등을 자동 검출하는 검수 도구",
  // OG 이미지(app/opengraph-image.tsx)를 트위터 large 카드로도 노출.
  twitter: {
    card: "summary_large_image",
    title: "CertQA — 자격검정 문항 검수",
    description: "자격검정 문항지의 오류를 자동 검출하는 검수 도구",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ko"
      className={`dark ${inter.variable} ${archivo.variable} h-full`}
      suppressHydrationWarning
    >
      <body className="min-h-full">
        <Providers>
          <div className="flex h-screen overflow-hidden">
            <Sidebar />
            <main className="flex-1 overflow-y-auto">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
