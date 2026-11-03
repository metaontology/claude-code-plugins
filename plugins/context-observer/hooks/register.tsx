/**
 * context-observer — Claude Mod
 *
 * 입력창 위에 두 줄을 그린다.
 *   - cache 줄: 직전 요청의 캐시 적중률, 캐시 만료까지 남은 시간, 자리 비움 압축까지 남은 시간
 *   - context 줄: 컨텍스트 사용률과 5시간·7일 사용량
 * /cache 는 턴별 캐시 표 창을 연다.
 *
 * 이 파일은 상태를 들고 이벤트를 잇기만 한다. 계산은 cache.ts·usage.ts, 그리기는 band.tsx·pane.tsx,
 * 설정 읽기는 settings.ts.
 *
 * cache 쪽은 davila7/claude-code-templates 의 prompt-cache-control(MIT, 3c468dd)을 바탕으로 한다.
 * 원본과 다른 점은 README.md 에 적었다.
 *
 * 옵션(pluginConfigs["context-observer@<마켓플레이스>"].options):
 *   ttl: "auto" | "5m" | "1h"   캐시 수명(기본 auto)
 *   warnSeconds: number         만료 경고 문턱(기본 60)
 *   compactAtTokens: number     만료된 캐시가 /compact 를 권하는 프롬프트 크기(기본 100000)
 *   band: boolean               cache 줄(기본 true, context 줄은 늘 그린다)
 *   status: boolean             입력창 아래 짧은 항목(기본 false)
 *   toast: boolean              만료 직전 토스트(기본 true)
 *   idleCompact: boolean        자리 비움 압축 카운트다운(기본 true)
 */
import type { Register } from 'claude-code'
import {
  accountOf,
  advise,
  COUNTDOWN_MARKS,
  decideTtl,
  fmtClock,
  fmtTokens,
  hitRatio,
  idleCompactAt,
  idlePolicy,
  isCachingDisabled,
  nextToastMark,
  observeTtl,
  positive,
  promptTokens,
  remainingMs,
} from './cache.ts'
import type { Account, CacheEnv, IdleCompact, Sample, Ttl } from './cache.ts'
import { cacheLine, contextLine } from './band.tsx'
import type { CacheView } from './band.tsx'
import { cachePane } from './pane.tsx'
import { readGlobalConfig, readSettings } from './settings.ts'
import { lineParts } from './usage.ts'
import type { Part } from './usage.ts'

const NAME = 'context-observer'
const PANE = 'cache'
const COMMAND = 'cache'
const KEEP = 200
// 이보다 작은 프롬프트는 캐시가 만료돼도 다시 쓰는 값이 작아 토스트로 끼어들지 않는다
const TOAST_MIN_TOKENS = 20_000

// ── cache 상태 ──
let samples: Sample[] = []
let ttl: Ttl = '5m'
let baseTtl: Ttl = '5m'
let pinned = false
let observed: Ttl | undefined
let setting: unknown
let account: Account = 'other'
let ttlSource = 'default'
let envSource = 'default'
let env: CacheEnv = {}
let idle: IdleCompact = idlePolicy({})
let timer: { cancel: () => void } | undefined
let lastKey = ''
let toastedFor = 0
let toastLevel = Infinity
let isPaneOpen = false

// ── context 상태 ──
let usageParts: Part[] | undefined

type Policy = { warnMs: number; compactAtTokens: number }

/** 지금 이 순간의 캐시 상태. */
function current(policy: Policy, now: number): CacheView {
  const last = samples[samples.length - 1]
  const prev = samples[samples.length - 2]
  const disabled = isCachingDisabled(last?.model ?? '', env)
  const advice = advise(last, prev, { ttl, ...policy }, now, disabled)
  const left = last ? remainingMs(last, ttl, now) : 0
  const idleAt = disabled ? undefined : idleCompactAt(last, ttl, idle, now)
  return { last, advice, left, idleAt, ttl, ttlSource }
}

/** 입력창 아래 짧은 항목(status 옵션). */
function shortLine(policy: Policy, now: number): string {
  const { last, advice, left } = current(policy, now)
  if (!last || advice.kind === 'off') return `cache: ${advice.text}`
  const clock = left > 0 ? ` · ${fmtClock(left)}` : ''
  return `cache ${Math.round(hitRatio(last) * 100)}%${clock}`
}

/** 계정이 바뀌었을 수 있으니(구독 한도 소진 → 사용량 크레딧) 수명을 다시 정하고, 요청 간격으로 바로잡는다. */
async function refreshTtl(usage: { rateLimits?: { kind: string; percentUsed: number }[] } | undefined, option: unknown, log: (t: string) => void) {
  account = accountOf(usage?.rateLimits ?? [])
  const choice = decideTtl(option, env, setting, account)
  baseTtl = choice.ttl
  envSource = choice.source
  if (observed === undefined) {
    ttl = baseTtl
    ttlSource = envSource
  }
  const seen = observeTtl(samples[samples.length - 2], samples[samples.length - 1], observed)
  if (seen !== observed) {
    observed = seen
    ttl = seen ?? baseTtl
    ttlSource = `observed from request timing; ${envSource} said ${baseTtl}`
    log(`${NAME}: cache lifetime is ${ttl} (${ttlSource})`)
  }
}

function resetCache() {
  samples = []
  lastKey = ''
  toastedFor = 0
  observed = undefined
}

export const register: Register = (on, options) => {
  const policy: Policy = {
    warnMs: positive(options.warnSeconds, 60) * 1000,
    compactAtTokens: positive(options.compactAtTokens, 100_000),
  }
  const showBand = options.band !== false
  const showStatus = options.status === true
  const wantToast = options.toast !== false
  const showIdle = options.idleCompact !== false

  on('session.start', async ($, e, next) => {
    const r = await next(e)
    resetCache()
    const none = () => undefined
    env = {
      enable1h: await $.env.get('ENABLE_PROMPT_CACHING_1H').catch(none),
      force5m: await $.env.get('FORCE_PROMPT_CACHING_5M').catch(none),
      ttlVar: await $.env.get('CLAUDE_CODE_PROMPT_CACHE_TTL').catch(none),
      disableAll: await $.env.get('DISABLE_PROMPT_CACHING').catch(none),
      disableHaiku: await $.env.get('DISABLE_PROMPT_CACHING_HAIKU').catch(none),
      disableSonnet: await $.env.get('DISABLE_PROMPT_CACHING_SONNET').catch(none),
      disableOpus: await $.env.get('DISABLE_PROMPT_CACHING_OPUS').catch(none),
    }
    pinned = options.ttl === '5m' || options.ttl === '1h'
    const settings = await readSettings($)
    setting = settings.promptCacheTtl
    const global = await readGlobalConfig($)
    idle = idlePolicy({
      minTokensVar: await $.env.get('CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS').catch(none),
      disableAuto: await $.env.get('DISABLE_AUTO_COMPACT').catch(none),
      disableAll: await $.env.get('DISABLE_COMPACT').catch(none),
      setting: settings.idleCompaction,
      autoCompact: settings.autoCompactEnabled ?? global.autoCompact,
      flag: global.flag,
    })

    // 한 번 읽은 사용량으로 계정(캐시 수명)과 context 줄을 함께 채운다
    const usage = await $.session.usage().catch(() => undefined)
    account = accountOf(usage?.rateLimits ?? [])
    const choice = decideTtl(options.ttl, env, setting, account)
    baseTtl = choice.ttl
    ttl = baseTtl
    envSource = choice.source
    ttlSource = envSource
    usageParts = usage?.context ? lineParts(usage.context, usage.rateLimits ?? []) : undefined

    await $.command
      .register({
        name: COMMAND,
        description: 'Prompt-cache usage per turn and the time left before it lapses (stop closes)',
        argumentHint: '[stop]',
        immediate: true,
      })
      .catch(err => $.ui.log(`${NAME}: /${COMMAND} not registered: ${err}`))
    $.ui.log(`${NAME} loaded: ${ttl} cache (${ttlSource}), /${COMMAND} opens the table`, { to: 'debug' })
    $.ui.log(`${NAME}: idle compaction ${idle.on ? 'on' : 'off'}, ${idle.why}${idle.known ? '' : ' (rollout flag not found)'}`, { to: 'debug' })

    // 카운트다운: 글자가 바뀔 때만 다시 그린다. 만료된 한가한 세션은 값이 들지 않는다
    timer?.cancel()
    timer = $.clock.every(1000, () => {
      const now = Date.now()
      const { last, advice, left, idleAt } = current(policy, now)
      const key = `${advice.kind}|${advice.text}|${left > 0 ? fmtClock(left) : ''}|${showIdle && idleAt ? fmtClock(Math.max(0, idleAt - now)) : ''}`
      if (key !== lastKey) {
        lastKey = key
        if (showStatus) $.ui.status(shortLine(policy, now))
        $.ui.invalidate('ui.render')
      }
      if (wantToast && last && left > 0 && promptTokens(last) >= TOAST_MIN_TOKENS) {
        if (toastedFor !== last.startedAt) {
          toastedFor = last.startedAt
          toastLevel = Infinity
        }
        // 첫 토스트는 warnSeconds, 그다음 10·3·2·1초. 늦은 틱은 가장 최근 문턱으로 건너뛴다
        const secs = Math.ceil(left / 1000)
        const mark = nextToastMark(secs, policy.warnMs / 1000, toastLevel)
        if (mark !== undefined) {
          toastLevel = mark
          const tail = secs <= COUNTDOWN_MARKS[0] ? 'send a message now' : `send a message to keep ${fmtTokens(promptTokens(last))} tokens warm`
          $.ui.toast(`cache expires in ${secs >= 60 ? fmtClock(left) : `${secs}s`}: ${tail}`)
        }
      }
    })
    $.ui.invalidate('ui.render')
    return r
  })

  on('session.end', async ($, e, next) => {
    // /clear 는 같은 프로세스에서 새 대화를 연다: 캐시도 새것이다
    if (e.reason === 'clear') {
      resetCache()
      ttl = baseTtl
      ttlSource = envSource
      $.ui.invalidate('ui.render')
      return next(e)
    }
    timer?.cancel()
    timer = undefined
    return next(e)
  })

  // 턴이 끝나거나 사용량 창이 움직일 때: context 줄
  on('session.measure', ($, e, next) => {
    usageParts = lineParts(e.context, e.rateLimits)
    $.ui.invalidate('ui.render')
    return next(e)
  })

  // 메인 루프 요청마다: 캐시가 그 요청에 무엇을 했나(서브에이전트는 접두가 달라 뺀다)
  on('turn.step', async function* ($, e, next) {
    if (e.agentId) return yield* next(e)
    const startedAt = Date.now()
    const r = yield* next(e)
    if (r.usage) {
      samples.push({
        turnId: e.turnId,
        index: e.index,
        model: r.usage.model || e.model,
        startedAt,
        read: r.usage.cache_read_input_tokens,
        write: r.usage.cache_creation_input_tokens,
        fresh: r.usage.input_tokens,
        output: r.usage.output_tokens,
      })
      if (samples.length > KEEP) samples = samples.slice(-KEEP)
      if (!pinned) {
        await refreshTtl(await $.session.usage().catch(() => undefined), options.ttl, t => $.ui.log(t, { to: 'debug' }))
      }
      lastKey = ''
      if (showStatus) $.ui.status(shortLine(policy, Date.now()))
      $.ui.invalidate('ui.render')
    }
    return r
  })

  on('command.run', { command: COMMAND }, async ($, e) => {
    if (e.args.trim().toLowerCase() === 'stop') {
      await $.ui.close({ id: PANE }).catch(() => undefined)
      isPaneOpen = false
      return { text: 'cache table closed' }
    }
    isPaneOpen = true
    await $.ui.open({ id: PANE, title: 'cache', focus: true })
    $.ui.invalidate('ui.render')
    const { advice } = current(policy, Date.now())
    return { text: `${ttl} cache (${ttlSource}) · ${advice.text} · /${COMMAND} stop closes` }
  })

  on('ui.close', async ($, e, next) => {
    if (e.id === PANE) isPaneOpen = false
    return next(e)
  })

  on('ui.press', async ($, e, next) => {
    if (e.plugin !== $.plugin.name || e.requestId !== PANE) return next(e)
    if (e.element === 'close') await $.ui.close({ id: PANE }).catch(() => undefined)
    return next(e)
  })

  // 입력창 위: cache 줄, context 줄, 그 아래에 다른 mod 가 그린 것
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const ui = $.ui.resolve(e)
    const now = Date.now()
    const lines = []
    // /cache 창이 열려 있으면 같은 내용이라 cache 줄은 쉰다
    if (showBand && !isPaneOpen) {
      const line = cacheLine(ui, current(policy, now), e.viewport?.columns ?? 100, showIdle, now)
      if (line) lines.push(line)
    }
    if (usageParts) lines.push(contextLine(ui, usageParts))
    const below = await next(e)
    if (lines.length === 0) return below
    const { Box } = ui
    return <Box flexDirection="column">{below ? [...lines, below] : lines}</Box>
  })

  on('ui.render', { component: 'Pane' }, async ($, e, next) => {
    if (e.requestId !== PANE) return next(e)
    const now = Date.now()
    return cachePane($.ui.resolve(e), e, current(policy, now), samples, idle, showIdle, policy.warnMs, now)
  })
}
