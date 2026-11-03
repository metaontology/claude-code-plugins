/**
 * pane.tsx — /cache 창. 남은 시간 막대, 직전 요청의 read·wrote·new 막대, 턴별 표를 그린다.
 * 원본 prompt-cache-control 의 Pane 그리기를 그대로 옮겼다.
 */
import type { UiRenderInput } from 'claude-code'
import { byTurn, fit, fmtClock, fmtTokens, hitRatio, lifeColor, lifeRatio, promptTokens, rowRatio, segments } from './cache.ts'
import type { IdleCompact, Sample } from './cache.ts'
import { ADVICE_COLOR, adviceIcon, isCounting } from './band.tsx'
import type { CacheView, Elements } from './band.tsx'

type PaneInput = { surface: string; props: { bodyColumns: number }; viewport?: { rows?: number } }

const idleClock = (idleAt: number, now: number) => (idleAt > now ? `⇣ ${fmtClock(idleAt - now)}` : '⇣ now')

export function cachePane(
  { Box, Text, Button }: Elements,
  e: PaneInput | UiRenderInput,
  v: CacheView,
  samples: readonly Sample[],
  idle: IdleCompact,
  showIdle: boolean,
  warnMs: number,
  now: number,
) {
  const input = e as PaneInput
  const { last, advice, left, idleAt, ttl, ttlSource } = v
  const width = Math.max(30, input.props.bodyColumns - 1)
  // HTML 은 연속 공백을 줄이고 끝 공백을 자른다: 터미널 밖에서는 no-break space 로 지킨다
  const sp = (t: string) => (input.surface === 'terminal' ? t : t.replace(/ /g, ' '))
  const all = byTurn(samples)
  const counting = !!last && isCounting(advice.kind)
  // 남은 시간 색: 초록 → 노랑 → 빨강
  const clockColor = counting ? lifeColor(left, ttl, warnMs) : undefined
  const stateColor = advice.kind === 'expired' || advice.kind === 'miss' ? 'red' : (clockColor ?? ADVICE_COLOR[advice.kind])
  const hitColor = (pct: number) => (pct >= 80 ? 'green' : pct >= 40 ? 'yellow' : 'red')
  // 막대는 블록 문자가 아니라 채운 Box 라서 HTML 에서도 칸 사이 틈이 없다
  const solid = (key: string, parts: [number, string | undefined][]) => (
    <Box key={key} flexDirection="row" height={1} flexShrink={0}>
      {parts.map(([w, c], i) => (w > 0 ? <Box key={`${key}:${i}`} width={w} height={1} flexShrink={0} backgroundColor={c} /> : null))}
    </Box>
  )
  const cell = (key: string, w: number, text: string, c?: string, bold = false) => (
    <Box key={key} width={w} flexShrink={0} justifyContent="flex-end">
      <Text color={c} bold={bold} dimColor={!c}>{sp(text)}</Text>
    </Box>
  )

  const barW = Math.min(width, 40)
  const life = lifeRatio(left, ttl)
  const lifeFilled = Math.round(life * barW)
  const [sr, sw, sn] = last ? segments(last.read, last.write, last.fresh, barW) : [0, 0, 0]
  const rows = all.slice(-Math.max(3, (input.viewport?.rows ?? 24) - 16))
  // 자리 비움 압축 줄이 왜 그렇게 말하는가
  const idleDetail = (at: number | undefined) => {
    if (!idle.on) return `${idle.why}`
    if (at !== undefined) return `if nobody types, Claude Code compacts at ${Math.round(idle.fraction * 100)}% of the 1h cache, ${idle.why}`
    if (ttl !== '1h') return `needs the 1h cache; this session's is ${ttl}`
    if (last && promptTokens(last) < idle.minTokens) return `waits for ${fmtTokens(idle.minTokens)} tokens; the prompt is ${fmtTokens(promptTokens(last))}`
    return `armed while the cache is warm, ${idle.why}`
  }
  const icon = adviceIcon(advice.kind)

  return (
    <Box flexDirection="column">
      <Box key="title" flexDirection="row" columnGap={1}>
        <Text bold color="cyan">{sp('⚡ PROMPT CACHE')}</Text>
        <Text dimColor>{sp(`· ${ttl} lifetime (${ttlSource})`)}</Text>
      </Box>

      <Box key="clock" flexDirection="column" marginTop={1}>
        <Text bold color={clockColor}>{sp(counting ? `⏱ ${left > 0 ? fmtClock(left) : '0:00'}` : '⏱ --:--')}</Text>
        {counting ? (
          <Box flexDirection="row" columnGap={1}>
            {solid('life', [[lifeFilled, clockColor], [barW - lifeFilled, 'gray']])}
            <Text dimColor>{sp(`${Math.round(life * 100)}%`)}</Text>
          </Box>
        ) : null}
      </Box>

      <Box key="advice" marginTop={1} flexDirection="column">
        <Text bold color={stateColor}>{sp(`${icon} ${advice.text}`)}</Text>
        {last ? <Text dimColor>{sp(fit(`${last.model} · prompt ${fmtTokens(promptTokens(last))} tokens`, width))}</Text> : null}
      </Box>

      {showIdle ? (
        <Box key="idle" marginTop={1} flexDirection="column">
          <Text bold color={idleAt !== undefined ? 'magenta' : undefined} dimColor={idleAt === undefined}>
            {sp(idleAt !== undefined ? `${idleClock(idleAt, now)} idle compaction` : `⇣ idle compaction ${idle.on ? 'on' : 'off'}`)}
          </Text>
          <Text dimColor>{sp(fit(idleDetail(idleAt), width))}</Text>
        </Box>
      ) : null}

      {last ? (
        <Box key="stack" flexDirection="column" marginTop={1}>
          <Box flexDirection="row" columnGap={1}>
            {solid('stack', [[sr, 'green'], [sw, 'yellow'], [sn, 'cyan']])}
            <Text bold color={hitColor(Math.round(hitRatio(last) * 100))}>{sp(`${Math.round(hitRatio(last) * 100)}% hit`)}</Text>
          </Box>
          <Box flexDirection="row" columnGap={2}>
            <Text color="green">{sp(`■ read ${fmtTokens(last.read)}`)}</Text>
            <Text color="yellow">{sp(`■ wrote ${fmtTokens(last.write)}`)}</Text>
            <Text color="cyan">{sp(`■ new ${fmtTokens(last.fresh)}`)}</Text>
          </Box>
        </Box>
      ) : null}

      <Box key="table" flexDirection="column" marginTop={1}>
        <Box key="head" flexDirection="row" columnGap={1}>
          {cell('h:turn', 4, 'turn', 'cyan', true)}
          {cell('h:steps', 5, 'steps', 'cyan', true)}
          {cell('h:read', 6, 'read', 'green', true)}
          {cell('h:wrote', 6, 'wrote', 'yellow', true)}
          {cell('h:new', 5, 'new', 'cyan', true)}
          {cell('h:hit', 4, 'hit', 'magenta', true)}
        </Box>
        {rows.length === 0 ? <Text dimColor>{sp('no requests yet')}</Text> : null}
        {rows.map((row, i) => {
          const n = all.length - rows.length + i + 1
          const pct = Math.round(rowRatio(row) * 100)
          return (
            <Box key={`t:${row.turnId}`} flexDirection="row" columnGap={1}>
              {cell(`c:turn:${row.turnId}`, 4, String(n))}
              {cell(`c:steps:${row.turnId}`, 5, String(row.steps))}
              {cell(`c:read:${row.turnId}`, 6, fmtTokens(row.read), 'green')}
              {cell(`c:wrote:${row.turnId}`, 6, fmtTokens(row.write), 'yellow')}
              {cell(`c:new:${row.turnId}`, 5, fmtTokens(row.fresh), 'cyan')}
              {cell(`c:hit:${row.turnId}`, 4, `${pct}%`, hitColor(pct), true)}
            </Box>
          )
        })}
      </Box>

      <Box key="foot" marginTop={1} flexDirection="column">
        <Button key="close" label="close" onPress={() => {}} />
        <Box key="legend" marginTop={1} flexDirection="column">
          <Text color="green">{sp('■ read: served by the cache')}</Text>
          <Text color="yellow">{sp('■ wrote: new cache entry')}</Text>
          <Text color="cyan">{sp('■ new: sent uncached')}</Text>
        </Box>
      </Box>
    </Box>
  )
}
