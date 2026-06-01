import type { MetadataRoute } from "next";

// PWA 매니페스트 — Next 가 자동으로 <link rel="manifest"> 를 주입한다.
// 다크 전용 앱이라 background/theme 모두 캔버스 색(#181818).
// 아이콘은 public/ 의 PNG 를 가리킨다(원본: assets/logo/certqa-appicon-*.svg).
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "CertQA — 자격검정 문항 검수",
    short_name: "CertQA",
    description:
      "자격검정 문항지의 오타·맞춤법·법령 오류 등을 자동 검출하는 검수 도구",
    start_url: "/",
    display: "standalone",
    background_color: "#181818",
    theme_color: "#181818",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      {
        src: "/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
