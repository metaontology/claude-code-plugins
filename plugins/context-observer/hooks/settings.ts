/**
 * settings.ts — mod 가 따르는 설정을 파일에서 읽는다. 읽기만 하고 쓰지 않는다.
 */
import type { EngineInterface } from 'claude-code'

export type Settings = { promptCacheTtl?: unknown; idleCompaction?: unknown; autoCompactEnabled?: unknown }

/** 각 설정을, 그것을 정한 첫 파일에서 읽는다(local → project → user 순). */
export async function readSettings($: EngineInterface): Promise<Settings> {
  const home = await $.env.get('HOME').catch(() => undefined)
  const cwd = await $.session.cwd().catch(() => undefined)
  const files = [cwd && `${cwd}/.claude/settings.local.json`, cwd && `${cwd}/.claude/settings.json`, home && `${home}/.claude/settings.json`]
  const out: Settings = {}
  for (const file of files) {
    if (!file) continue
    try {
      const json = JSON.parse(await $.fs.read(file))
      if (out.promptCacheTtl === undefined && (json.promptCacheTtl === '5m' || json.promptCacheTtl === '1h')) out.promptCacheTtl = json.promptCacheTtl
      if (out.idleCompaction === undefined && typeof json.idleCompaction === 'boolean') out.idleCompaction = json.idleCompaction
      if (out.autoCompactEnabled === undefined && typeof json.autoCompactEnabled === 'boolean') out.autoCompactEnabled = json.autoCompactEnabled
    } catch {
      // 없거나 못 읽으면 다음 파일
    }
  }
  return out
}

/**
 * Claude Code 전역 설정(~/.claude.json)에서 두 값만 꺼낸다:
 * 자리 비움 압축의 배포 플래그(tengu_sunny_locket)와 autoCompactEnabled. 그 밖의 값은 들고 있지 않는다.
 */
export async function readGlobalConfig($: EngineInterface): Promise<{ flag?: unknown; autoCompact?: unknown }> {
  const dir = await $.env.get('CLAUDE_CONFIG_DIR').catch(() => undefined)
  const home = await $.env.get('HOME').catch(() => undefined)
  const file = dir ? `${dir}/.claude.json` : home ? `${home}/.claude.json` : undefined
  if (!file) return {}
  try {
    const json = JSON.parse(await $.fs.read(file))
    const flag = json?.cachedGrowthBookFeatures?.tengu_sunny_locket
    return { flag: flag && typeof flag === 'object' ? flag : undefined, autoCompact: json?.autoCompactEnabled }
  } catch {
    return {}
  }
}
