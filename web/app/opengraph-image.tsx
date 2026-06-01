import { ImageResponse } from 'next/og'
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'

export const alt = 'CertQA — 자격검정 문항 오류 자동 검출'
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

const dotGrid =
  'url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIzMiIgaGVpZ2h0PSIzMiIgdmlld0JveD0iMCAwIDMyIDMyIj48Y2lyY2xlIGN4PSIxNiIgY3k9IjE2IiByPSIxLjIiIGZpbGw9IiMzZWNmOGUiIGZpbGwtb3BhY2l0eT0iMC4wNiIvPjwvc3ZnPg==)'

export default async function Image() {
  // 로컬 폰트는 web/ 기준 경로에서 읽는다.
  const [archivoData, notoData] = await Promise.all([
    readFile(join(process.cwd(), 'assets/fonts/ArchivoBlack-Regular.ttf')),
    readFile(join(process.cwd(), 'assets/fonts/NotoSansKR-600-subset.woff')),
  ])
  // Archivo Black 정적 컷 — satori 는 variable 폰트에서 크래시하므로 정적 사용.
  // 단일 weight(400) 글리프가 곧 디스플레이 블랙이라 워드마크 굵기와 일치.
  const archivo = {
    name: 'Archivo',
    data: archivoData,
    weight: 900 as const,
    style: 'normal' as const,
  }
  const noto = {
    name: 'Noto Sans KR',
    data: notoData,
    weight: 600,
    style: 'normal' as const,
  }

  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          position: 'relative',
          backgroundColor: '#181818',
          color: '#ededed',
        }}
      >
        <div
          style={{
            position: 'absolute',
            inset: 0,
            backgroundImage: dotGrid,
            backgroundRepeat: 'repeat',
            backgroundSize: '32px 32px',
          }}
        />
        <div
          style={{
            position: 'absolute',
            inset: 0,
            backgroundImage:
              'radial-gradient(circle at center, rgba(62, 207, 142, 0.08) 0, rgba(62, 207, 142, 0.04) 24%, rgba(24, 24, 24, 0) 58%)',
          }}
        />
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '28px',
            zIndex: 1,
          }}
        >
          <svg width={150} height={150} viewBox="0 0 24 24">
            <path
              fill="#3ecf8e"
              d="M8.85 21.35L0.95 13.45L4.75 9.65L8.85 13.75L20.25 2.35L23.05 6.15L8.85 21.35Z"
            />
          </svg>
          <div
            style={{
              display: 'flex',
              fontFamily: 'Archivo',
              fontWeight: 900,
              fontSize: 120,
              letterSpacing: '-0.02em',
              lineHeight: 1,
            }}
          >
            <span style={{ color: '#ededed' }}>Cert</span>
            <span style={{ color: '#3ecf8e' }}>QA</span>
          </div>
        </div>
        <div
          style={{
            marginTop: '36px',
            fontFamily: 'Noto Sans KR',
            fontWeight: 600,
            fontSize: 36,
            letterSpacing: '-0.01em',
            color: '#8f8f8f',
            zIndex: 1,
          }}
        >
          자격검정 문항 오류 자동 검출
        </div>
      </div>
    ),
    {
      ...size,
      fonts: [archivo, noto],
    }
  )
}
