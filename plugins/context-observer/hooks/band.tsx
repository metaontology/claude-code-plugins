/**
 * band.tsx — 입력창 위 두 줄을 그린다. 상태는 들고 있지 않고, register.tsx 가 넘긴 값만 그린다.
 *
 *   ● cache   100% [cached: r 271k, uncached: w 878 new 2] | timeout 56:59/1h | auto compact 50:49
 *   ● context  28% [279.4k/1m] | 𝟓hr 28% | 𝟕day 13%
 *
 * 한 줄을 한 Text 안의 색 조각으로 그린다. 조각마다 Text 를 나란히 두면 좁을 때 조각 안에서
 * 줄이 바뀌어 여러 줄이 되고, JSX fragment 는 Box 로 그려져 Text 안에 둘 수 없다.
 */
import type { EngineInterface } from 'claude-code'
import { fit, fmtClock, fmtTokens, hitRatio, promptTokens } from './cache.ts'
import type { Advice, Sample, Ttl } from './cache.ts'
import { padAfterLabel } from './usage.ts'
import type { Part } from './usage.ts'

export type Elements = ReturnType<EngineInterface['ui']['resolve']>

/** 캐시 상태 한 순간. register.tsx 의 current() 가 만든다. */
export type CacheView = {
  last: Sample | undefined
  advice: Advice
  /** 캐시 만료까지 남은 ms. 0 이면 만료(또는 셀 것이 없음). */
  left: number
  /** 자리 비움 압축이 일어날 시각(ms). 없으면 undefined. */
  idleAt: number | undefined
  ttl: Ttl
  ttlSource: string
}

export const ADVICE_COLOR: Record<Advice['kind'], string | undefined> = {
  warm: 'green',
  soon: 'yellow',
  expired: 'red',
  miss: 'red',
  off: undefined,
  cold: undefined,
  uncached: undefined,
}

/** 상태 아이콘: warm ●, soon ▲, expired·miss ✖, 그 밖 ○. */
export function adviceIcon(kind: Advice['kind']): string {
  if (kind === 'warm') return '●'
  if (kind === 'soon') return '▲'
  if (kind === 'off' || kind === 'cold' || kind === 'uncached') return '○'
  return '✖'
}

/** 카운트다운이 의미 있는 상태인가: 셀 캐시 항목이 있을 때만. */
export const isCounting = (kind: Advice['kind']) => kind !== 'uncached' && kind !== 'off' && kind !== 'cold'

/** cache 줄. 요청 기록이 없고 캐싱도 꺼져 있지 않으면 undefined(줄을 그리지 않는다). */
export function cacheLine({ Text }: Elements, v: CacheView, columns: number, showIdle: boolean, now: number) {
  const { last, advice, left, idleAt, ttl } = v
  if (!last) return advice.kind === 'off' ? <Text dimColor>{fit(`cache: ${advice.text}`, columns)}</Text> : undefined

  const color = ADVICE_COLOR[advice.kind]
  const pct = `${Math.round(hitRatio(last) * 100)}%`
  const sp = () => <Text> </Text>
  const sep = () => <Text dimColor> | </Text>
  const pieces = [
    <Text bold color={color}>{adviceIcon(advice.kind)}</Text>,
    sp(),
    <Text bold color="cyan">cache</Text>,
    <Text>{padAfterLabel('cache', pct)}</Text>,
    <Text bold color={color}>{pct}</Text>,
    sp(),
    // 적중률 = r ÷ (r + w + new): 이번 요청에서 캐시가 내준 것(r)과 못 내준 것(w·new)
    columns >= 90 ? (
      <Text>{`[cached: r ${fmtTokens(last.read)}, uncached: w ${fmtTokens(last.write)} new ${fmtTokens(last.fresh)}]`}</Text>
    ) : (
      <Text dimColor>{`[${fmtTokens(promptTokens(last))} tok]`}</Text>
    ),
  ]
  if (isCounting(advice.kind)) {
    pieces.push(sep(), <Text color="cyan">timeout</Text>, sp(), <Text>{`${left > 0 ? fmtClock(left) : '0:00'}/${ttl}`}</Text>)
  }
  if (showIdle && idleAt !== undefined) {
    pieces.push(sep(), <Text color="magenta">auto compact</Text>, sp(), <Text>{idleAt > now ? fmtClock(idleAt - now) : 'now'}</Text>)
  } else {
    pieces.push(sep(), <Text dimColor>{advice.text}</Text>)
  }
  return <Text wrap="truncate-end">{pieces}</Text>
}

/** context 줄. */
export function contextLine({ Text }: Elements, parts: Part[]) {
  const pieces = parts.map(p => (p.color ? <Text color={p.color} bold={p.text === '●'}>{p.text}</Text> : <Text>{p.text}</Text>))
  return <Text wrap="truncate-end">{pieces}</Text>
}
