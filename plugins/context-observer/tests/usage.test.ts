// 실행: claude plugin test <플러그인 폴더>  (dev 에서는 docs/guide/개발-가이드.md 의 「시험」)
import { describe, expect, test } from 'claude-code/testing'

import { formatLine, lineParts } from '../hooks/usage.ts'

describe('context 줄', () => {
  test('요청한 꼴로 줄을 만든다', () => {
    const line = formatLine({ tokens: 208_300, window: 1_000_000, percent: 21 }, [
      { kind: 'five_hour', percentUsed: 26.7 },
      { kind: 'seven_day', percentUsed: 12 },
    ])
    expect(line).toBe('● context  21% [208.3k/1m] | 𝟓hr 26% | 𝟕day 12%')
  })

  test('퍼센트는 4칸 오른쪽 정렬: 100% 와 5% 도 [ 가 같은 열에 선다', () => {
    const at = (percent: number) => formatLine({ tokens: 1, window: 1_000_000, percent }, [])!.indexOf('[')
    expect(at(5)).toBe(at(100))
    expect(at(28)).toBe(at(100))
  })

  test('구독이 아니어서 사용량 창이 없으면 -- 로 둔다', () => {
    const line = formatLine({ tokens: 45_000, window: 200_000, percent: 23 }, [])
    expect(line).toBe('● context  23% [45k/200k] | 𝟓hr -- | 𝟕day --')
  })

  test('창 크기를 모르면(응답 전) 줄이 없다', () => {
    expect(lineParts({ window: 0 }, [])).toBeUndefined()
  })

  test('dash-statusline 과 같은 색을 입힌다', () => {
    const parts = lineParts({ tokens: 750_000, window: 1_000_000, percent: 75 }, [
      { kind: 'five_hour', percentUsed: 95 },
      { kind: 'seven_day', percentUsed: 12 },
    ])!
    const colorOf = (text: string) => parts.find(p => p.text === text)?.color
    expect(colorOf('●')).toBe('green') // cache 줄의 ● 와 같은 색
    expect(colorOf('context')).toBe('#afd7af') // effort 라벨과 같은 색
    expect(colorOf('75%')).toBe('#ffff87') // 70% 이상 노랑
    expect(colorOf(' [750k/1m]')).toBeUndefined() // 대괄호 안은 색 없음
    expect(colorOf('𝟓hr')).toBe('#5fafff')
    expect(colorOf('95%')).toBe('red') // 90% 이상 빨강
    expect(colorOf('𝟕day')).toBe('#d7005f')
    expect(colorOf('12%')).toBe('green')
  })
})

describe('입력창 위', () => {
  test('context 줄을 그리고, 요청 전이라 cache 줄은 없다', async ($, on) => {
    on('session.measure', (_, e) => ({ changed: e.changed }))
    on('ui.invalidate', () => ({ value: undefined }))
    // 엔진 몫: 다른 mod 가 없을 때 band 는 비어 있다
    on('ui.render', ($, e) => $.ui.resolve(e).Box({}))

    await $.session.measure({
      context: { tokens: 208_300, window: 1_000_000, percent: 21 },
      rateLimits: [
        { kind: 'five_hour', percentUsed: 26 },
        { kind: 'seven_day', percentUsed: 12 },
      ],
      changed: ['context', 'rateLimits'],
    })

    const ui = await $.ui.mount({
      plugin: 'context-observer',
      component: 'AbovePrompt',
      surface: 'terminal',
      props: { hasSurvey: false, isWorking: false, maxRows: 20, bodyColumns: 80 },
    })
    // 한 줄이 한 Text 라 바깥 Text 는 줄 전체, 안쪽 조각은 따로 찾힌다
    expect((await ui.find({ type: 'Text', text: /^● context/ }))?.text).toBe('● context  21% [208.3k/1m] | 𝟓hr 26% | 𝟕day 12%')
    expect(await ui.find({ type: 'Text', text: /^ \[208\.3k\/1m\]$/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /cache/ })).toBeUndefined()
    await ui.unmount()
  })
})
