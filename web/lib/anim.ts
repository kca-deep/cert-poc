/**
 * 공용 진입(entrance) 애니메이션 — 화면 간 "컴포넌트 등장 효과" 통일.
 * tw-animate-css(app/globals.css 임포트) 유틸을 사용한다.
 *
 * 사용:
 *   <div className={cn(ENTER, "...")} style={staggerDelay(i)}>...</div>
 * 단일 섹션은 staggerDelay 없이 ENTER 만, 리스트/순차 섹션은 index 로 stagger.
 */

/** fade-in + 아래에서 살짝 슬라이드업, 300ms ease-out. mount 시 1회 재생. */
export const ENTER =
  "animate-in fade-in-0 slide-in-from-bottom-2 duration-300 ease-out fill-mode-both";

/** index 기반 등장 지연 (기본 60ms 간격). inline style 로 적용. */
export function staggerDelay(index: number, stepMs = 60): React.CSSProperties {
  return { animationDelay: `${index * stepMs}ms` };
}
