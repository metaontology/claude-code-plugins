/**
 * usage.ts — context 줄의 순수 계산. `$` 도 엔진도 쓰지 않는다.
 *
 * 'context  21% [208.3k/1m] | 𝟓hr 26% | 𝟕day 12%' 를 색 조각으로 만든다.
 * 색은 ~/.claude/dash-statusline 의 default 테마를 따른다.
 */
import type { SessionContextUsage, SessionRateLimit } from 'claude-code'

//   ok   \033[32m              → green
//   warn \033[38;5;228m        → #ffff87
//   crit \033[31m              → red
//   blue \033[38;5;75m         → #5fafff (𝟓hr 라벨)
//   purple_red \033[38;5;161m  → #d7005f (𝟕day 라벨)
//   effort \033[38;5;151m      → #afd7af (context 라벨 — 3번째 줄 effort 라벨과 같은 색)
export const OK = 'green'
const WARN = '#ffff87'
const CRIT = 'red'
const BLUE = '#5fafff'
const PURPLE_RED = '#d7005f'
const LABEL = '#afd7af'

/** 라벨 칸 너비. cache 줄도 이 너비로 퍼센트 열을 맞춘다('cache   ' = 'context '). */
export const LABEL_WIDTH = 8
/** 퍼센트 칸 너비. '100%' 가 들어가는 4칸에 오른쪽 정렬한다. */
export const PCT_WIDTH = 4

/** 한 조각: 글자와 색. 색이 없으면 터미널 기본색. */
export type Part = { text: string; color?: string }

/** 70% 이상 노랑, 90% 이상 빨강, 그 아래 초록 — dash-statusline 과 같은 문턱. */
export function pctColor(pct: number): string {
  if (pct >= 90) return CRIT
  if (pct >= 70) return WARN
  return OK
}

/** 라벨 뒤 공백: 라벨과 합쳐 LABEL_WIDTH 칸, 그 뒤 퍼센트를 PCT_WIDTH 칸에 오른쪽 정렬. */
export function padAfterLabel(label: string, pct: string): string {
  return ' '.repeat(Math.max(1, LABEL_WIDTH - label.length) + Math.max(0, PCT_WIDTH - pct.length))
}

/** 토큰 수를 102.3k · 1m 꼴로 줄인다. */
export function compact(n: number): string {
  if (n >= 1_000_000) return trim(n / 1_000_000) + 'm'
  if (n >= 1_000) return trim(n / 1_000) + 'k'
  return String(n)
}

// 소수 한 자리까지만 두고 .0 은 뗀다.
function trim(x: number): string {
  return (Math.round(x * 10) / 10).toString()
}

// 사용량 창 하나: 라벨은 고정색, 퍼센트는 문턱색. 읽은 값이 없으면 '--'.
function windowParts(label: string, labelColor: string, limits: SessionRateLimit[], kind: string): Part[] {
  const w = limits.find(l => l.kind === kind)
  // dash-statusline 처럼 소수점은 버린다.
  const pct = w ? Math.floor(w.percentUsed) : undefined
  return [
    { text: label, color: labelColor },
    { text: ' ' },
    pct === undefined ? { text: '--' } : { text: `${pct}%`, color: pctColor(pct) },
  ]
}

/** context 줄의 색 조각. 창 크기를 모르면(아직 응답 전) undefined. */
export function lineParts(context: SessionContextUsage, limits: SessionRateLimit[]): Part[] | undefined {
  if (!context.window) return undefined
  const percent = context.percent ?? 0
  const pct = `${percent}%`
  return [
    // cache 줄의 머리 ● 와 열을 맞춘다. 색은 그 ● 가 평소(warm) 쓰는 green.
    { text: '●', color: OK },
    { text: ' ' },
    { text: 'context', color: LABEL },
    { text: padAfterLabel('context', pct) },
    { text: pct, color: pctColor(percent) },
    // 대괄호 안은 색 없이 둔다.
    { text: ` [${compact(context.tokens ?? 0)}/${compact(context.window)}]` },
    { text: ' | ' },
    ...windowParts('𝟓hr', BLUE, limits, 'five_hour'),
    { text: ' | ' },
    ...windowParts('𝟕day', PURPLE_RED, limits, 'seven_day'),
  ]
}

/** 색을 뺀 한 줄. 테스트에서 쓴다. */
export function formatLine(context: SessionContextUsage, limits: SessionRateLimit[]): string | undefined {
  return lineParts(context, limits)?.map(p => p.text).join('')
}
