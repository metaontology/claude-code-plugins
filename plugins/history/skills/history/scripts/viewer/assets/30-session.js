/* 세션 축 화면 — 목록 · 대화 · 검색 · 매치 강조 · 원본 경로 복사.
 *
 * 셸에 꽂는 것은 App.provide('s', {list, search, body, foot}) 하나이고, 삭제 계약은
 * Destructive.register('s', …)로 따로 등록한다. 아무것도 window에 노출하지 않는다.
 */
(function () {
  'use strict';

  // 오른쪽 말풍선으로 가는 종류. 목록의 💬 수를 세는 정의와 같아야 한다
  const SAID_KINDS = ['user', 'slash_command', 'local_command'];

  /* 좌측 마커는 흐름 쪽(Claude · 도구)에만 붙는다. 사용자 발언은 자리가 곧 표식이다.
     ✦는 이모지가 아니라 기호라 CSS로 색이 먹는다 — 30-session.css가 accent를 준다.
     도구 쪽 마커는 아래 트리가 갖는다 */
  const MARKERS = {
    assistant: '✦'
  };

  /* 도구 항목의 **갈래 · 표식 · 설명 · 집계 순서를 이 트리 하나가 모두 준다.**
     따로 두면 표식을 더할 때 고칠 자리가 넷이 되고, 한쪽만 고치면 화면이 거짓말을 한다.

     큰 갈래의 판정 규칙은 dash-statusline의 `_classify`와 같다 — 한 화면에서 같은 것이
     같은 그림이어야 하므로 분류를 새로 만들지 않는다.

     Agent·Skill의 자식은 내장인가 사람이 가져온 것인가를 가른다. 그 표식이 마커 열이
     아니라 이름 앞에 서는 이유는 마커 열이 큰 갈래 하나를 위해 폭이 고정된 자리이기
     때문이다. 세부는 이름과 붙어 있어야 무엇의 성질인지가 드러난다.

     `label`은 집계 줄에 서고 `hint`는 마우스를 올렸을 때 나온다. 자식에서 둘이 다른 것은
     읽는 자리가 다르기 때문이다 — 집계에서는 부모(`서브에이전트`) 밑이라 `내장`으로
     충분하지만, 툴팁은 홀로 읽히므로 무엇의 내장인지가 있어야 한다 */
  const TOOL_TREE = [
    { key: 'plain', mark: '🔧', label: '도구' },
    { key: 'Agent', mark: '😎', label: '서브에이전트', kids: [
      { key: 'agentBuiltin', mark: 'ඞ', label: '내장', hint: '내장 에이전트' },
      { key: 'agentOther', mark: '👾', label: '그 밖', hint: '에이전트' }
    ] },
    { key: 'mcp', mark: '🧊', label: 'MCP 도구' },
    { key: 'Skill', mark: '🪚', label: '스킬', kids: [
      { key: 'skillBuiltin', mark: '𓌜', label: '내장', hint: '내장 스킬' },
      { key: 'skillOther', mark: '🪓', label: '그 밖', hint: '스킬' }
    ] },
    { key: 'TodoWrite', mark: '📋', label: '할 일 목록' }
  ];

  // 갈래 키로 노드를 찾는 색인과, 도구 이름이 곧 키인 갈래. 둘 다 트리에서 만든다
  const NODE = {};
  TOOL_TREE.forEach(function (node) {
    NODE[node.key] = node;
    (node.kids || []).forEach(function (kid) { NODE[kid.key] = kid; });
  });
  // `plain`·`mcp`는 도구 이름이 아니라 이름의 생김새로 판정하므로 뺀다
  const NAMED_KEYS = TOOL_TREE
    .map(function (node) { return node.key; })
    .filter(function (key) { return key !== 'plain' && key !== 'mcp'; });

  /* 내장 여부만 가른다 — 마켓플레이스에서 설치했든 직접 만들었든 비내장은 하나다.

     **agent만 이름을 열거한다.** 내장 agent에는 "파일이 없다"는 근거가 없어 여집합으로
     정의할 수 없다. 목록은 기억으로 채우지 않는다 — Claude Code 소스의 사본이
     dash-statusline 작업공간의 `references/claude-code-main/`에 있고,
     `grep -rn "agentType:" src/tools/AgentTool/built-in/`이 답이다 */
  const BUILTIN_AGENTS = [
    'Explore', 'Plan', 'general-purpose',
    'claude-code-guide', 'statusline-setup', 'verification'
  ];

  // 순서가 곧 우선순위다. 세션 하나는 가장 앞선 그룹에 한 번만 들어간다
  const GROUPS = ['파일 경로 매치', '제목 매치', '스킬 · 커맨드 매치', '본문 매치'];

  // 본문 인용 조각에서 매치 앞뒤로 남기는 글자 수
  const LEAD = 20;
  const TRAIL = 24;
  // 복사 결과를 버튼 문구로 알리는 시간
  const FLASH_MS = 1200;

  /* search()가 기억하고 list()가 비운다. 셸은 body(id)에 질의를 넘기지 않으므로,
     한 번의 재렌더에서 list() → search() → body() 순으로 불리는 것에 기댄다 */
  let query = '';

  // 현재 본문의 <mark> 목록과 그중 몇 번째를 보고 있는가
  let hits = [];
  let hitAt = 0;
  let hitLabel = null;

  function el(tag, text, cls) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }

  function sessions() {
    return App.data.sessions || [];
  }

  /* 매번 선형 탐색한다. 40여 개이므로 색인을 두지 않는다 — sessions는 삭제로 바뀌는
     배열이고, 색인을 두면 그것을 무효화할 자리가 remove와 refresh 둘로 갈린다 */
  function findSession(id) {
    const all = sessions();
    for (let i = 0; i < all.length; i++) if (all[i].id === id) return all[i];
    return null;
  }

  function titleOf(session) {
    return session.title || '(제목 없음)';
  }

  /* 살아 있는 목록은 셸이 SSE로 받아 App.live에 둔다. embed에 없으므로 첫 페인트에서는
     비어 있고, file://에서는 끝까지 비어 있다.

     **창 하나에 원소 하나이므로 같은 id가 여럿일 수 있다** — 창 둘이 같은 세션을 열고
     있는 상태다. 존재 판정은 그래도 그대로다 */
  function isLive(id) {
    return (App.live || []).indexOf(id) >= 0;
  }

  // 그 세션을 열고 있는 창 수. 존재 판정과 같은 배열을 보므로 둘이 갈라질 여지가 없다
  function liveCount(id) {
    return (App.live || []).filter((live) => live === id).length;
  }

  /* 살아 있는 세션에는 **모두 같은 자리에 같은 배지**가 붙는다. 현재 세션도 예외가
     아니다 — "지금 무엇이 돌고 있는가"는 한 열을 위에서 아래로 훑어 답이 나와야 하고,
     현재 세션만 다른 표식을 달면 그 열에 구멍이 생긴다.

     창이 둘 이상이면 그 수를 뒤에 붙인다. 두 창의 발언이 한 jsonl에 섞여 쌓이는데
     화면이 그 사실을 말하지 않으면 사용자는 모르고 계속한다. **1일 때는 붙이지 않는다** —
     거의 모든 행이 그 상태이므로 `1`은 정보를 더하지 않고 자리만 차지한다 */
  function liveBadge(id) {
    const count = liveCount(id);
    if (!count) return null;
    if (count < 2) return el('span', '● 실행중', 'srow-live');
    const badge = el('span', `● 실행중 ${count}`, 'srow-live');
    badge.title = `이 세션을 ${count}곳에서 동시에 열고 있습니다.`;
    return badge;
  }

  /* 이 창이 지금 보고 있는 세션. 셸이 SSE로 받아 App.current에 두고, 아직 오지 않았으면
     null이므로 embed에 굳은 값(이 파일을 만든 세션)으로 떨어진다.

     **판정하는 자리를 여기 하나로 모은다.** 배지와 체크박스 부재가 같은 사실을 따로
     계산하면 한쪽만 폴백을 빠뜨렸을 때 배지도 체크박스도 없는 행이 생긴다 */
  function currentId() {
    return App.current === null ? (App.data.current || '') : App.current;
  }

  /* 현재 세션 표식은 둘째 줄 오른쪽 끝에 따로 둔다. 실행중과 **뜻이 다르기 때문이다** —
     하나는 "돌고 있다"이고 하나는 "이 화면을 연 창이 지금 보고 있는 것이 그것이다"이다.
     같은 자리를 놓고 다투게 두면 둘 중 하나를 못 쓰게 된다.

     세션에 붙는 것이 아니라 창을 따라다니므로, `/resume`으로 옮기면 배지도 옮겨간다 */
  function currentBadge(id) {
    return id === currentId() ? el('span', '현재', 'srow-now') : null;
  }

  /* 아이콘만으로는 무엇을 센 값인지 알 수 없다. 목록 행의 절대 시각과 같은 방식으로
     title에 담는다 — 이 화면에 이미 있는 관례다.

     아이콘과 숫자를 한 span에 담으므로 설명이 뜨는 영역도 둘을 합친 것이다. 아이콘만
     감싸면 마우스를 올릴 표적이 글자 하나 크기가 된다 */
  function countNode(text, label) {
    const node = el('span', text, 'srow-count');
    node.title = label;
    return node;
  }

  // ── 시각 ─────────────────────────────────────────────────────────────────
  /* 모델은 원본 ISO 문자열을 그대로 넘긴다. 표기는 화면의 일이다 */

  function parseTs(ts) {
    if (!ts) return null;
    const date = new Date(ts);
    return isNaN(date.getTime()) ? null : date;
  }

  function pad(value) {
    return value < 10 ? `0${value}` : String(value);
  }

  function absolute(date) {
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
         + ` ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  function clockOf(date) {
    return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  }

  function relative(date) {
    const minutes = Math.floor((Date.now() - date.getTime()) / 60000);
    if (minutes < 1) return '방금';
    if (minutes < 60) return `${minutes}분 전`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}시간 전`;
    if (hours < 48) return '어제';
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days}일 전`;
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  }

  // ── 목록 행 ──────────────────────────────────────────────────────────────

  /* 호출마다 노드를 새로 만든다. 셸의 addRow가 클릭 리스너를 붙이고 aria-current를
     세우는데 지우는 코드가 없으므로, 캐시하면 리스너가 겹쳐 붙고 한 번 현재였던 행이
     영원히 현재로 남는다. 표식도 같은 이유로 매번 새로 받는다 — 실패 사유가 그 안에 있다 */
  function rowNode(session, reason) {
    const row = el('div', undefined, 'srow');

    const head = el('div', undefined, 'srow-head');
    const badge = Destructive.mark('s', session.id);
    if (badge) head.appendChild(badge);
    head.appendChild(el('span', titleOf(session), 'srow-title'));
    const running = liveBadge(session.id);
    if (running) head.appendChild(running);
    row.appendChild(head);

    const meta = el('div', undefined, 'srow-meta');
    const date = parseTs(session.ts);
    /* 시각이 빈 세션에도 이 칸을 만든다. 빼면 그 행만 뒤의 두 값이 왼쪽으로 당겨져
       세로 줄이 어긋난다 — 폭을 고정한 이유가 사라진다 */
    const when = el('span', date ? relative(date) : '', 'srow-when');
    // 절대 시각은 목록에서 자리를 쓰지 않고 마우스를 올렸을 때만 나온다
    if (date) when.title = absolute(date);
    meta.appendChild(when);
    meta.appendChild(countNode(`💬 ${session.user_count}`, '사용자 프롬프트 수'));
    meta.appendChild(countNode(`📄 ${(session.files || []).length}`, '건드린 파일 수'));
    // 컨텍스트 사용량은 25-usage.js가 갖는다. 그 칸도 `.srow-count`이므로 세로 줄이 이어진다
    meta.appendChild(Usage.badge(session));
    const here = currentBadge(session.id);
    if (here) meta.appendChild(here);
    row.appendChild(meta);

    if (reason) row.appendChild(reason);
    return row;
  }

  function list() {
    query = '';
    return sessions().map((session) => ({ id: session.id, node: rowNode(session) }));
  }

  // ── 목록 패널의 꼬리 슬롯 ────────────────────────────────────────────────
  /* 세션 하나가 비어 있는지로 조건을 걸면 실질적으로 보이지 않는다 — Claude Code는
     세션을 만든 순간 첫 발언을 함께 적어 entries가 0인 채로 목록에 걸리는 창이 거의
     없다(실측). 그래서 특정 행이 아니라 **목록 전체의 안내**로 옮긴다. 검색 여부와
     무관하게 그리는 이유는 00-app.js의 addSlot이 그렇게 정했기 때문이다 —
     20-viewer/030-auto-memory.md가 먼저 쓴 머리·꼬리 슬롯을 여기서도 그대로 쓴다 */
  function foot() {
    return el('div', '세션 대화기록은 30일 이후 자동삭제됩니다.', 'slist-foot-note');
  }

  // ── 검색 ─────────────────────────────────────────────────────────────────
  /* 질의는 셸이 이미 앞뒤 공백을 없애고 소문자로 만들어 넘긴다 */

  function matches(text, needle) {
    return String(text || '').toLowerCase().indexOf(needle) >= 0;
  }

  function excerpt(text, at, length) {
    const from = Math.max(0, at - LEAD);
    const to = Math.min(text.length, at + length + TRAIL);
    const piece = text.slice(from, to).replace(/\s+/g, ' ').trim();
    return (from > 0 ? '…' : '') + piece + (to < text.length ? '…' : '');
  }

  function entryHits(session, needle) {
    let count = 0;
    let snippet = '';
    (session.entries || []).forEach((entry) => {
      const text = String(entry.text || '');
      const low = text.toLowerCase();
      let at = low.indexOf(needle);
      while (at >= 0) {
        if (!count) snippet = excerpt(text, at, needle.length);
        count++;
        at = low.indexOf(needle, at + needle.length);
      }
    });
    return { count, snippet };
  }

  function reasonNode(text, extra) {
    const node = el('div', text, 'srow-why');
    if (extra > 0) node.appendChild(el('span', `+${extra}`, 'srow-more'));
    return node;
  }

  /* 앞선 그룹부터 판정하고 걸리면 거기서 끝낸다. 중복을 허용하면 같은 세션이 두 번
     나오고 그룹 개수의 합이 걸린 세션 수보다 커져 그 수를 읽을 수 없다 */
  function classify(session, needle) {
    const paths = (session.files || []).filter((path) => matches(path, needle));
    if (paths.length) {
      return { group: 0, reason: reasonNode(`📄 ${paths[0]}`, paths.length - 1) };
    }

    // 제목은 행에 이미 보이므로 이유를 따로 붙이지 않는다
    if (matches(session.title, needle)) return { group: 1, reason: null };

    // 이유 줄의 표식은 칩의 것과 같다. 같은 것이 화면에서 두 그림이면 안 된다
    const named = [];
    (session.skills || []).forEach((skill) => {
      if (matches(skill, needle)) named.push(`${chipIcon('Skill')} ${skill}`);
    });
    (session.commands || []).forEach((command) => {
      if (matches(command, needle)) named.push(`${chipIcon('commands')} ${command}`);
    });
    if (named.length) {
      return { group: 2, reason: reasonNode(named[0], named.length - 1) };
    }

    const found = entryHits(session, needle);
    if (found.count) {
      return { group: 3, reason: reasonNode(`💬 "${found.snippet}"`, found.count - 1) };
    }
    return null;
  }

  function search(raw) {
    query = raw || '';
    const buckets = [[], [], [], []];
    if (query) {
      sessions().forEach((session) => {
        const hit = classify(session, query);
        if (!hit) return;
        buckets[hit.group].push({ id: session.id, node: rowNode(session, hit.reason) });
      });
    }
    // 매치가 없는 그룹도 머리와 (0)이 보인다. "그 이유로는 걸리지 않았다"가
    // 결과가 없는 것과 다른 사실이기 때문이다
    return GROUPS.map((label, index) => ({ label, rows: buckets[index] }));
  }

  // ── 매치 강조 ────────────────────────────────────────────────────────────
  /* 렌더 전에 원문에 마커를 넣지 않는다 — 코드펜스 안에 그대로 실려 보이고, 표의
     셀 구분자에 걸치면 표가 문단으로 렌더된다. 렌더 뒤에 텍스트 노드를 쪼갠다.
     pre·code 안도 제외하지 않는다. 검색이 원문 전문을 스캔하므로 코드 안의 매치도
     진짜 매치이고, 노드를 쪼개는 것은 코드의 텍스트를 바꾸지 않는다 */

  function highlight(root, needle) {
    if (!needle) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    const targets = [];
    let node;
    // 훑는 도중에 쪼개면 walker가 새로 생긴 노드를 다시 만난다. 모아 두고 나중에 쪼갠다
    while ((node = walker.nextNode()) !== null) {
      if (node.nodeValue.toLowerCase().indexOf(needle) >= 0) targets.push(node);
    }
    targets.forEach((text) => { splitInto(text, needle); });
  }

  function splitInto(text, needle) {
    const value = text.nodeValue;
    const low = value.toLowerCase();
    const frag = document.createDocumentFragment();
    let last = 0;
    let at = low.indexOf(needle);
    while (at >= 0) {
      if (at > last) frag.appendChild(document.createTextNode(value.slice(last, at)));
      const hit = el('mark', value.slice(at, at + needle.length));
      frag.appendChild(hit);
      hits.push(hit);
      last = at + needle.length;
      at = low.indexOf(needle, last);
    }
    if (last < value.length) frag.appendChild(document.createTextNode(value.slice(last)));
    text.parentNode.replaceChild(frag, text);
  }

  function navNode() {
    const nav = el('div', undefined, 'hitnav');
    // 클래스를 주지 않는다. 이 노드는 변수로 직접 참조하고, 색·크기는 `.hitnav`가 준다
    hitLabel = el('span', '');
    nav.appendChild(hitLabel);
    nav.appendChild(navButton('∧', -1));
    nav.appendChild(navButton('∨', 1));
    return nav;
  }

  function navButton(text, delta) {
    const button = el('button', text);
    button.type = 'button';
    button.addEventListener('click', () => { step(delta); });
    return button;
  }

  function step(delta) {
    if (hits.length < 2) return;
    hits[hitAt].classList.remove('hit-on');
    // 끝에서 다음을 누르면 처음으로 돈다. 막다른 길을 만들면 몇 번째인지 세게 된다
    hitAt = (hitAt + delta + hits.length) % hits.length;
    hits[hitAt].classList.add('hit-on');
    hits[hitAt].scrollIntoView({ block: 'center' });
    showAt();
  }

  function showAt() {
    hitLabel.textContent = `매치 ${hitAt + 1}/${hits.length}`;
  }

  // ── 원본 경로 복사 ───────────────────────────────────────────────────────

  /* 조립 재료인 sessions_dir는 셸이 embed에 담았다. 구분자는 그 값에서 읽는다 —
     /로 고정하면 Windows에서 구분자가 섞인 경로가 복사된다 */
  function sourcePath(id) {
    const dir = String(App.data.sessions_dir || '').replace(/[\\/]+$/, '');
    const sep = dir.indexOf('\\') >= 0 ? '\\' : '/';
    return `${dir}${sep}${id}.jsonl`;
  }

  /* file://은 secure context가 아니므로 navigator.clipboard가 없다. 폐기 예정 API지만
     그쪽에서 동작하는 유일한 수단이고, 대안은 읽기 전용에서 복사를 포기하는 것뿐이다 */
  function legacyCopy(text) {
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.top = '-1000px';
    document.body.appendChild(area);
    area.select();
    let ok = false;
    try {
      ok = document.execCommand('copy');
    } catch (error) {
      ok = false;
    }
    document.body.removeChild(area);
    return ok;
  }

  function flash(button, text) {
    const was = button.dataset.label || button.textContent;
    button.dataset.label = was;
    button.textContent = text;
    setTimeout(() => { button.textContent = was; }, FLASH_MS);
  }

  /* "탐색기에서 보기"와 같은 아이콘(사각+화살표)이다. 여는 대상이 다르다는 것은 이미
     위치(상단 헤더 vs 대화 머리)와 `title` 문구가 말하므로, 아이콘까지 다른 모양을 쓰면
     "탐색기로 연다"는 같은 동작에 배워야 할 그림이 둘이 된다. 00-app.js의 ICON_REVEAL과
     같은 값이지만 상수를 공유하지는 않는다 — 각 자산이 IIFE로 스코프가 갈려 있다 */
  const ICON_REVEAL = '<path d="M17 13.5V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h5.5"'
    + ' stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
    + '<path d="M14 3h7v7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"'
    + ' stroke-linejoin="round"/>'
    + '<path d="M21 3L11 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>';

  /* 모든 세션이 같은 슬러그 디렉토리 아래 있으므로 세션 ID를 서버에 보낼 필요가 없다 —
     요청은 항상 `{target: 'sessions_dir'}`다. `reveal_supported`가 거짓이거나 읽기
     전용이면 그리지 않는다(00-app.js의 initReveal과 같은 규칙) */
  function revealButton() {
    if (!App.data.reveal_supported || App.readonly) return null;
    const button = el('button', undefined, 'shead-reveal');
    button.type = 'button';
    button.innerHTML = '<svg viewBox="0 0 24 24" width="12" height="12"'
      + ' fill="none" aria-hidden="true">' + ICON_REVEAL + '</svg>';
    button.title = '세션 폴더 열기';
    button.setAttribute('aria-label', '세션 폴더 열기');
    button.addEventListener('click', () => {
      const token = new URLSearchParams(location.search).get('t') || '';
      fetch(`/api/reveal?t=${encodeURIComponent(token)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target: 'sessions_dir' })
      }).catch(() => {});
    });
    return button;
  }

  function copyButton(id) {
    const button = el('button', '경로 복사', 'shead-copy');
    button.type = 'button';
    button.addEventListener('click', () => {
      const path = sourcePath(id);
      /* execCommand는 사용자 제스처 안에서만 동작한다. clipboard의 실패를 기다렸다가
         부르면 제스처가 이미 끝나 있으므로 catch가 아니라 가용성으로 가른다 */
      if (window.isSecureContext && navigator.clipboard) {
        navigator.clipboard.writeText(path).then(
          () => { flash(button, '복사됨'); },
          () => { flash(button, '복사 실패'); }
        );
      } else {
        flash(button, legacyCopy(path) ? '복사됨' : '복사 실패');
      }
    });
    return button;
  }

  // ── 대화 화면 ────────────────────────────────────────────────────────────

  function header(session) {
    const head = el('div', undefined, 'shead');
    head.appendChild(el('div', titleOf(session), 'shead-title'));

    const line = el('div', undefined, 'shead-meta');
    const date = parseTs(session.ts);
    if (date) {
      line.appendChild(el('span', absolute(date)));
      line.appendChild(el('span', relative(date)));
    }
    // 화면에 앞자리만 보이는 것은 머리 한 줄이 길어지지 않게 하기 위한 것이고,
    // 복사되는 값과는 무관하다
    line.appendChild(el('span', `${session.id.slice(0, 8)}…`, 'shead-id'));
    const reveal = revealButton();
    if (reveal) line.appendChild(reveal);
    line.appendChild(copyButton(session.id));
    head.appendChild(line);
    // 게이지 줄. 응답 기록이 없는 세션에서는 null이므로 아무것도 서지 않는다
    const usage = Usage.gauge(session);
    if (usage) head.appendChild(usage);
    return head;
  }

  function listPanel(values) {
    const items = el('ul', undefined, 'chip-list');
    if (values.length) {
      values.forEach((value) => { items.appendChild(el('li', value)); });
    } else {
      items.appendChild(el('li', '없음', 'chip-none'));
    }
    return items;
  }

  /* 도구 항목을 한 번 훑어 두 가지를 함께 만든다 — 갈래별 **호출 수**(자식은 부모에도
     함께 세어진다)와 갈래별 **이름별 횟수**. 칩 여덟이 이 값을 나눠 쓰므로 여기서 한 번만
     센다. 이름은 부른 대상이 있으면 그것이다 — `Agent`·`Skill`에서는 도구 이름이 아니라
     무엇을 불렀는지가 답이기 때문이다 */
  function toolStats(entries) {
    const counts = {};
    const names = {};
    (entries || []).forEach((entry) => {
      if (entry.kind !== 'tool') return;
      const key = toolKey(entry.tool);
      counts[key] = (counts[key] || 0) + 1;
      const kid = kindKey(entry.tool, entry.target);
      if (kid) counts[kid] = (counts[kid] || 0) + 1;
      const name = entry.target || entry.tool;
      if (!names[key]) names[key] = {};
      names[key][name] = (names[key][name] || 0) + 1;
    });
    return { counts: counts, names: names };
  }

  // 이름별 횟수를 많은 순으로. 같으면 이름순이라 실행마다 순서가 흔들리지 않는다
  function countPanel(map) {
    const names = Object.keys(map || {});
    if (!names.length) return listPanel([]);
    names.sort((a, b) => (map[b] - map[a]) || (a < b ? -1 : 1));

    const list = el('dl', undefined, 'tally');
    names.forEach((name) => {
      list.appendChild(el('dt', name));
      list.appendChild(el('dd', String(map[name])));
    });
    return list;
  }

  // 갈래별 사용 횟수를 트리로 세운다. 자식은 부모 아래 들여쓴다
  function toolsPanel(counts) {
    const list = el('dl', undefined, 'tools');
    function row(node, isKid) {
      const count = counts[node.key] || 0;
      const mark = el('dt', node.mark, isKid ? 'tools-mark tools-kid' : 'tools-mark');
      const desc = el('dd', undefined, count ? '' : 'tools-zero');
      desc.appendChild(el('span', node.label));
      desc.appendChild(el('span', String(count), 'tools-n'));
      mark.title = hintOf(node.key);
      desc.title = hintOf(node.key);
      list.appendChild(mark);
      list.appendChild(desc);
    }
    TOOL_TREE.forEach((node) => {
      row(node, false);
      (node.kids || []).forEach((kid) => { row(kid, true); });
    });
    return list;
  }

  /* 칩 여덟. 순서가 곧 화면 순서다.

     `list`를 가진 둘은 세션 값을 그대로 늘어놓고, 나머지 다섯은 갈래 이름이 곧 `key`라
     `toolStats`의 이름별 횟수를 찾아 쓴다. 마지막 하나만 갈래를 가로지르는 트리다.

     버튼에 붙는 수는 **몇 종을 썼는가**이고 내역의 수는 **몇 번 불렀는가**다. 층이 다르다 —
     `도구 6`은 여섯 종류를 썼다는 뜻이고, 그 안의 `Edit 18`이 그중 하나를 18번이다 */
  const CHIP_SPECS = [
    { key: 'files', label: '건드린 파일', icon: '📄', list: (s) => s.files || [] },
    { key: 'commands', label: '커맨드', icon: '>_', list: (s) => s.commands || [] },
    { key: 'plain', label: '도구' },
    { key: 'Agent', label: '서브에이전트' },
    { key: 'mcp', label: 'MCP' },
    { key: 'Skill', label: '스킬' },
    { key: 'TodoWrite', label: 'TODO' },
    { key: 'stats', label: 'Tool 통계', icon: '📊', wide: true }
  ];

  /* 칩에 서는 표식. 갈래 다섯은 `icon`을 갖지 않고 **트리의 것을 그대로 쓴다** — 버튼의
     🔧과 대화 항목의 🔧이 같은 값이라야 둘이 같은 것을 가리키는 줄 안다.
     검색 결과의 이유 줄도 이 함수를 거친다. 한 화면에 같은 것의 그림이 둘이면 안 된다 */
  function chipIcon(key) {
    for (let i = 0; i < CHIP_SPECS.length; i++) {
      if (CHIP_SPECS[i].key === key) return CHIP_SPECS[i].icon || markOf(key);
    }
    return '';
  }

  // 버튼에 붙는 수. `Tool 통계`는 갈래를 가로지르므로 셀 것이 없다
  function chipCount(spec, session, stats) {
    if (spec.wide) return null;
    if (spec.list) return spec.list(session).length;
    return Object.keys(stats.names[spec.key] || {}).length;
  }

  function chipPanel(spec, session, stats) {
    if (spec.wide) return toolsPanel(stats.counts);
    if (spec.list) return listPanel(spec.list(session));
    return countPanel(stats.names[spec.key]);
  }

  /* 어느 칩이 열려 있는가. 모듈 변수라 세션을 바꿔도 같은 칩이 열린 채로 남는다 —
     여러 세션의 같은 값을 연달아 보는 것이 이 화면에서 흔한 동선이다 */
  let openChip = '';

  /* 칩 여덟은 **한 번에 하나만 열리고, 버튼 줄은 움직이지 않는다.** 내용은 버튼 아래의
     한 칸에 나온다. details/summary를 쓰지 않는 이유가 여기 있다 — 그것은 내용을
     자기 안에 담으므로 열린 칩이 넓어지며 옆 버튼을 밀어낸다.

     네 내용을 모두 만들어 두고 보이는 것만 바꾼다. 만들었다 지우면 `body()`가 거는
     검색 강조가 그 뒤에 만들어진 내용에는 걸리지 않는다 */
  function chips(session) {
    const wrap = el('div', undefined, 'chipwrap');
    const bar = el('div', undefined, 'chips');
    const panel = el('div', undefined, 'chip-panel');
    const stats = toolStats(session.entries);
    const buttons = {};
    const panes = {};

    function paint() {
      CHIP_SPECS.forEach((spec) => {
        const on = spec.key === openChip;
        buttons[spec.key].setAttribute('aria-expanded', on ? 'true' : 'false');
        panes[spec.key].hidden = !on;
      });
      panel.className = openChip ? 'chip-panel open' : 'chip-panel';
    }

    CHIP_SPECS.forEach((spec) => {
      const count = chipCount(spec, session, stats);
      const head = `${chipIcon(spec.key)} ${spec.label}`;
      // 수가 없는 칩(`Tool 통계`)은 흐려지지 않는다. 0인 것과 셀 것이 없는 것은 다르다
      const button = el('button', count === null ? head : `${head} ${count}`,
                        count === 0 ? 'chip-tab chip-tab-zero' : 'chip-tab');
      button.type = 'button';
      // 같은 버튼을 다시 누르면 닫히고, 다른 버튼을 누르면 그쪽으로 옮겨간다
      button.addEventListener('click', () => {
        openChip = openChip === spec.key ? '' : spec.key;
        paint();
      });
      buttons[spec.key] = button;
      bar.appendChild(button);

      const pane = el('div', undefined, 'chip-pane');
      pane.appendChild(chipPanel(spec, session, stats));
      panes[spec.key] = pane;
      panel.appendChild(pane);
    });

    paint();
    wrap.appendChild(bar);
    wrap.appendChild(panel);
    return wrap;
  }

  /* 도구 라벨과 커맨드는 마크다운으로 렌더하지 않는다. 경로·명령·JSON 조각이라
     `**`가 든 명령이 굵게 바뀌고 […](…)꼴 인자가 링크가 되어 원문과 다른 것을 보여준다 */
  function isVerbatim(kind) {
    return kind === 'tool' || kind === 'slash_command' || kind === 'local_command';
  }

  function isSaid(kind) {
    return SAID_KINDS.indexOf(kind) >= 0;
  }

  // 큰 갈래. 도구 이름이 그대로 키가 아니면 이름의 생김새로 가른다
  function toolKey(name) {
    const key = String(name || '');
    if (NAMED_KEYS.indexOf(key) >= 0) return key;
    return key.indexOf('mcp__') === 0 ? 'mcp' : 'plain';
  }

  /* skill의 내장 여부는 **여집합**으로 가른다 — 내장은 바이너리에 등록되어 파일이 없고,
     사람이 가져온 것만 파일을 가진다. 이름을 열거하면 릴리스마다 낡지만 이 방식은 낡지
     않는다.

     둘 중 하나면 비내장이다 —
       ① 이름에 콜론이 있다. `plugin:skill`이든 중첩 디렉토리(`git:git-commit`)든
          파일에서 왔다는 뜻이고, **디스크 상태와 무관하게 언제나 옳다**
       ② `local_skills`에 있다. 산출물을 만들 때 파이썬이 디스크를 훑어 담은 목록이다 */
  function isLocalSkill(target) {
    if (target.indexOf(':') >= 0) return true;
    return (App.data.local_skills || []).indexOf(target) >= 0;
  }

  /* 세부 갈래. 두 도구가 아니거나 부른 대상이 없으면 빈 문자열이고,
     그때는 세부 칸이 아예 서지 않는다 */
  function kindKey(name, target) {
    if (!target) return '';
    if (name === 'Agent') {
      return BUILTIN_AGENTS.indexOf(target) >= 0 ? 'agentBuiltin' : 'agentOther';
    }
    if (name === 'Skill') {
      return isLocalSkill(target) ? 'skillOther' : 'skillBuiltin';
    }
    return '';
  }

  function markOf(key) {
    return key && NODE[key] ? NODE[key].mark : '';
  }

  // 툴팁 문구. 자식은 홀로 읽히므로 `hint`를 갖고, 없으면 집계 줄의 `label`이 그 일을 한다
  function hintOf(key) {
    const node = key ? NODE[key] : null;
    return node ? (node.hint || node.label) : '';
  }

  function bodyNode(entry) {
    if (isVerbatim(entry.kind)) return el('span', entry.text || '', 'ent-label');
    return renderMarkdown(entry.text || '');
  }

  /* 사용자 발언 — 말풍선과 시각 두 자식뿐이다. 마커도 시각 열도 없다 */
  function saidNode(entry) {
    const row = el('div', undefined, `ent ent-said ent-${entry.kind}`);
    const bubble = el('div', undefined, isVerbatim(entry.kind) ? 'said-bubble ent-raw' : 'said-bubble md');
    bubble.appendChild(bodyNode(entry));
    row.appendChild(bubble);

    const date = parseTs(entry.ts);
    if (date) row.appendChild(el('span', clockOf(date), 'said-at'));
    return row;
  }

  /* Claude의 말과 도구 — 시각 · 마커 · 본문 세 열 */
  function flowNode(entry) {
    const row = el('div', undefined, `ent ent-${entry.kind}`);
    const date = parseTs(entry.ts);
    // 도구 항목에는 시각을 붙이지 않는다. 열은 비워 두므로 마커 열이 흔들리지 않는다
    row.appendChild(el('span', entry.kind === 'tool' || !date ? '' : clockOf(date), 'ent-at'));
    /* 표식과 이름에 설명을 붙인다. 목록의 💬·📄와 같은 취지다 — 뜻을 묻는 자리가 곧
       그것이 보이는 자리이므로, 범례를 찾아 눈이 화면을 떠나지 않아도 된다 */
    const isTool = entry.kind === 'tool';
    const key = isTool ? toolKey(entry.tool) : '';
    const kid = isTool ? kindKey(entry.tool, entry.target) : '';
    const mark = el('span', isTool ? markOf(key) : (MARKERS[entry.kind] || '·'), 'ent-mark');
    if (isTool) mark.title = hintOf(key);
    row.appendChild(mark);

    const text = el('div', undefined, isVerbatim(entry.kind) ? 'ent-text ent-raw' : 'ent-text md');
    let name = '';
    if (isTool && entry.tool) {
      // 세부 표식이 서면 이름 자리도 부른 대상으로 바뀐다. 도구 이름은 마커 열이 이미 말한다
      name = kid ? entry.target : entry.tool;
      if (kid) {
        const kindNode = el('span', markOf(kid), 'ent-kind');
        kindNode.title = hintOf(kid);
        text.appendChild(kindNode);
      }
      const toolNode = el('span', name, 'ent-tool');
      // 이름에는 그 항목의 가장 좁은 뜻을 붙인다 — 세부가 있으면 그쪽이다
      toolNode.title = hintOf(kid || key);
      text.appendChild(toolNode);
    }
    /* 라벨이 이름을 되풀이하는 항목이 있다 — `Skill` 호출의 라벨 규칙 3순위가 `skill`
       키를 잡으므로 라벨과 대상이 같은 문자열이 된다. 그때는 라벨을 그리지 않는다.
       검색 강조는 이름 노드에도 걸리므로(`highlight`가 대화 전체를 훑는다) 잃는 것이 없다 */
    if (entry.text !== name) text.appendChild(bodyNode(entry));
    row.appendChild(text);
    return row;
  }

  function entryNode(entry) {
    return isSaid(entry.kind) ? saidNode(entry) : flowNode(entry);
  }

  function body(id) {
    const session = findSession(id);
    if (!session) return null;

    hits = [];
    hitAt = 0;
    hitLabel = null;

    const wrap = el('div', undefined, 'sbody');
    const head = header(session);
    wrap.appendChild(head);

    // 마크다운 렌더는 세션을 여는 이 순간에만 일어난다. 목록을 그릴 때 entries를 훑지 않는다
    const marked = el('div', undefined, 'smarked');
    marked.appendChild(chips(session));
    const talk = el('div', undefined, 'talk');
    const entries = session.entries || [];
    if (entries.length) {
      entries.forEach((entry) => { talk.appendChild(entryNode(entry)); });
    } else {
      /* 방금 시작해 아직 아무 말도 오가지 않은 세션이다. 머리와 칩은 남긴다 —
         어느 세션인지와 원본 경로는 대화가 없어도 답할 수 있는 사실이고,
         그것까지 지우면 잘못 연 것처럼 보인다 */
      talk.appendChild(el('div', '아직 대화 내역이 없습니다.', 'talk-empty'));
    }
    marked.appendChild(talk);

    highlight(marked, query);
    wrap.appendChild(marked);

    if (hits.length) {
      hits[0].classList.add('hit-on');
      head.appendChild(navNode());
      showAt();
    }
    return wrap;
  }

  // ── 등록 ─────────────────────────────────────────────────────────────────
  /* 20-destructive.js와 00-app.js가 파일명 순서로 앞서므로 둘 다 이미 있고,
     셸의 route()는 DOMContentLoaded에서 불리므로 그때는 등록이 끝나 있다 */

  App.provide('s', { list, search, body, foot });

  Destructive.register('s', {
    endpoint: '/api/sessions/delete',
    noun: '세션',
    action: '삭제',
    confirmVerb: '영구 삭제',
    warning: 'jsonl 원본이 지워집니다. 되돌릴 수 없습니다.',
    describe(id) {
      const session = findSession(id);
      if (!session) return document.createTextNode(id);
      const date = parseTs(session.ts);
      const parts = [titleOf(session)];
      if (date) parts.push(relative(date));
      parts.push(`💬${session.user_count}`, `📄${(session.files || []).length}`);
      return document.createTextNode(parts.join('  ·  '));
    },
    /* 화면에서 체크박스가 사라지는 것은 실수를 막고, 서버의 같은 가드는 우회를 막는다.
       돌려주는 문자열은 화면에 그려지지 않는다 — 왜 고를 수 없는지는 이 행의 배지가
       이미 말한다. 두 판정이 갈라지지 않도록 currentBadge · liveBadge와 같은 근거를
       같은 순서로 본다 */
    blocked(id) {
      if (id === currentId()) return '진행 중인 세션';
      return isLive(id) ? '실행 중인 세션' : '';
    },
    // 목록을 여기서 다시 그리지 않는다. 파괴적 연산 UI가 App.refresh()를 부른다
    remove(id) {
      App.data.sessions = sessions().filter((session) => session.id !== id);
    }
  });
})();
