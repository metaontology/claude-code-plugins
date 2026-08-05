/* 컨텍스트 사용량 표시 — 목록 행의 % 칸과 대화 머리의 게이지 줄.
 *
 * 전역 `Usage` 하나를 노출한다. `30-session.js`가 이것을 부르므로 파일 번호가 그보다
 * 앞이다 — 자산은 파일명 순서로 이어붙으므로 그 순서가 곧 로드 순서다.
 *
 * 값은 `session/usage.py`가 숫자로만 준다. 여기서 하는 일은 그 숫자를 표기로 바꾸는 것이고,
 * 윈도우 판정 같은 도메인 규칙은 파이썬 쪽에 있다.
 */
(function () {
  'use strict';

  // 이 이상이면 막대와 숫자가 경고색이다. 70% 단계를 두지 않는 근거는
  // docs/dev-plans/20-viewer/080-context-gauge.md의 「색 단계를 둘로 두는 이유」
  const HOT_PCT = 90;

  /* `30-session.js`의 것과 같은 세 줄이다. 가져오려면 그것을 또 어딘가에 노출해야 하고,
     전역을 하나 더 늘리는 비용이 세 줄의 중복보다 크다 */
  function el(tag, text, cls) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }

  /* dash-statusline `statuses/context/__init__.py`의 `_fmt_tok`을 옮긴 것이다.
     두 플러그인은 따로 설치되므로 참조할 수 없어 복사한다. 같은 값을 다르게 적으면
     한 사람이 두 화면을 견주지 못한다 */
  function fmtTok(n) {
    if (n < 1000) return String(n);
    if (n < 1000000) {
      const s = (n / 1000).toFixed(1);
      return (s.endsWith('.0') ? s.slice(0, -2) : s) + 'k';
    }
    const s = (n / 1000000).toFixed(1);
    return (s.endsWith('.0') ? s.slice(0, -2) : s) + 'm';
  }

  /* 모델 ID를 표시명으로. 표를 두지 않는다 — 이름이 ID에서 기계적으로 나오고, 표를 두면
     모델이 나올 때마다 고칠 곳이 둘이 된다 */
  function modelName(id) {
    const bare = String(id || '').replace(/^claude-/, '');
    // 20260401 같은 날짜 토큰은 이름에 넣지 않는다
    const parts = bare.split('-').filter(function (p) { return !/^\d{8}$/.test(p); });
    const head = parts.shift() || '';
    // 첫 토큰이 이름이 아니면 규칙 밖의 ID다. 원문을 보여주는 편이 낫다
    if (!/^[a-z]+$/.test(head)) return String(id || '');
    const rest = parts.join('.');
    const name = head.charAt(0).toUpperCase() + head.slice(1);
    return rest ? name + ' ' + rest : name;
  }

  function usageOf(session) {
    return (session && session.usage) || null;
  }

  // 응답 기록이 있는가. current가 0인 것으로 판정하지 않는다 — 첫 응답이 아직 오지 않은
  // 세션과 값이 정말 0인 세션이 갈리지 않는다
  function hasRecord(usage) {
    return !!(usage && usage.models && usage.models.length);
  }

  function pctOf(usage) {
    if (!usage || !usage.window) return 0;
    return Math.round((usage.current / usage.window) * 100);
  }

  // 분모. 추정이면 앞에 물결이 붙는다
  function denomOf(usage) {
    const loose = usage.window_basis === 'assumed' || usage.window_basis === 'unknown';
    return (loose ? '~' : '') + fmtTok(usage.window);
  }

  function lastModel(usage) {
    return usage.models[usage.models.length - 1];
  }

  function badgeTitle(usage) {
    if (!hasRecord(usage)) {
      return '컨텍스트 사용량입니다. 이 세션에는 응답 기록이 없습니다.';
    }
    const head = '컨텍스트 사용량입니다. ';
    if (usage.window_basis === 'assumed') {
      return head + '분모는 ' + modelName(lastModel(usage))
        + '의 지원 상한이며 이 세션이 그 크기로 돌았다는 기록은 없습니다.';
    }
    if (usage.window_basis === 'unknown') {
      return head + lastModel(usage)
        + '가 MODEL_WINDOWS에 없어 기본값 ' + fmtTok(usage.window) + '로 계산했습니다.';
    }
    return head + fmtTok(usage.current) + '/' + fmtTok(usage.window);
  }

  /* 목록 행의 칸. **항상 노드를 돌려준다** — 빼면 그 행만 뒤가 왼쪽으로 당겨져 세로 줄이
     어긋난다. 클래스는 `30-session.css`의 `.srow-count`를 물려받는다. 그 파일의
     `countNode`를 부를 수 없어서(그 함수는 축 IIFE 안에 있다) 클래스만 같게 둔다 */
  function badge(session) {
    const usage = usageOf(session);
    const node = el('span', '🧩 ' + (usage ? pctOf(usage) : 0) + '%', 'srow-count');
    node.title = badgeTitle(usage);
    return node;
  }

  function barNode(pct) {
    const track = el('span', undefined, 'usage-bar');
    track.setAttribute('aria-hidden', 'true');
    const fill = el('span', undefined, 'usage-fill');
    // 100%를 넘겨 그리지 않는다. window가 실제보다 작게 추정된 경우가 있다
    fill.style.width = Math.min(100, Math.max(0, pct)) + '%';
    track.appendChild(fill);
    return track;
  }

  function gaugeLine(usage) {
    const pct = pctOf(usage);
    const line = el('div', undefined,
                    'shead-usage' + (pct >= HOT_PCT ? ' usage-hot' : ''));
    line.appendChild(el('span', '🧩'));
    line.appendChild(barNode(pct));

    const num = el('span',
                   pct + '% [' + fmtTok(usage.current) + '/' + denomOf(usage) + ']',
                   'usage-num');
    // 둘이 갈리는 것은 compaction이 일어난 세션뿐이다. 같으면 말할 것이 없다
    if (usage.peak !== usage.current) {
      num.title = '최대 ' + fmtTok(usage.peak) + '까지 찼습니다.';
    }
    line.appendChild(num);

    if (usage.window_basis === 'unknown') {
      const flag = el('span', '⚠', 'usage-flag');
      flag.title = lastModel(usage) + '는 MODEL_WINDOWS에 없습니다. 분모가 기본값 '
        + fmtTok(usage.window) + '이므로 표에 추가해야 합니다.';
      line.appendChild(flag);
    }

    const model = el('span', '✨ ' + modelName(lastModel(usage)), 'usage-model');
    if (usage.models.length > 1) {
      model.title = '이 세션에서 쓰인 모델입니다 — ' + usage.models.join(' · ');
    }
    line.appendChild(model);
    return line;
  }

  /* 대화 머리의 게이지 줄. 응답 기록이 없으면 `null`이다 */
  function gauge(session) {
    const usage = usageOf(session);
    return hasRecord(usage) ? gaugeLine(usage) : null;
  }

  window.Usage = { badge: badge, gauge: gauge };
})();
