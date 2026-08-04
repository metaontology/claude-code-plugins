/* 뷰어 셸의 런타임 — embed 데이터 · 축 탭 · 해시 라우팅 · 검색 골격 · 패널 드래그 · SSE.
 *
 * 자산은 하나의 <script>로 이어붙으므로 파일마다 IIFE로 감싸고 공개할 것만 window에 붙인다.
 * 축별 화면은 뒤따르는 파일(20-* · 30-* · 40-*)이 App.provide로 꽂는다.
 */
(function () {
  'use strict';

  /* 축이 둘이라는 것과 각 축이 무엇인지는 셸이 안다. 항목 수도 셸이 직접 센다 —
     페이로드를 소유한 쪽이 셸이므로 이미 셸의 지식이다. 축 스크립트가 등록하는
     형태로 두면 그것이 없는 단계에서 탭 자체가 사라져 셸을 관측할 수 없다 */
  const AXES = [
    { key: 's', label: '세션', count: (d) => d.sessions.length },
    { key: 'm', label: 'auto-memory', count: (d) => d.memory.items.length }
  ];

  // 브라우저에 남기는 설정의 키 접두사. 파일로 연 화면에서만 쓴다
  const CONFIG_PREFIX = 'history.viewer.';
  const PANE_MIN = 180;
  const PANE_MAX_RATIO = 0.7;
  // EventSource의 자동 재시도가 이 시간 안에 성공하지 못하면 끊긴 것으로 본다
  const DISCONNECT_GRACE = 3000;
  /* 파비콘의 면 색. **탭 줄에서 프로젝트를 가르는 것은 이 색이다** — 제목은 탭이 좁아지면
     잘리지만 아이콘은 남는다.

     색을 런타임에 계산하지 않고 미리 뽑은 열을 박는다. 계산하면 검수되지 않은 색이 나오고,
     이 열은 흰 글자와 4.64:1~5.71:1로 전부 AA를 넘는 것이 확인된 값이다.

     그 균일함이 `oklch(0.53 0.14 h)`에서 온다 — L을 고정하고 색상만 돌린 값이라 어느
     색상에서도 지각 밝기가 같다. `hsl`의 L로 같은 일을 하면 대비가 2.68:1~9.80:1로
     흩어져 연두에서는 흰 글자가 읽히지 않고 남색은 혼자 시커멓다(`docs/guides/color/`).

     색상 간격이 균등한 30°가 아닌 이유는 눈이 청록~파랑 구간을 덜 가르기 때문이다.
     균등하게 놓으면 그 구간에 넷이 몰려 서로 비슷해진다.

     **열한 번째 프로젝트부터 색이 겹친다.** 겹쳐도 글자와 제목이 남으므로 같아지지 않는다 */
  const FAVICON_COLORS = [
    '#ae4440', '#a35400', '#826a00', '#3e7e23', '#008462',
    '#008096', '#1f6db9', '#6f59b5', '#904c9b', '#a64374'
  ];
  // 경로를 지우기 전에 남겨 두는 여유. 0이면 경로가 테마 버튼에 붙어 한 줄로 뭉쳐 보인다
  const PATH_MARGIN = 8;
  /* 설정 저장을 다시 보내는 횟수와 간격. 서버 쪽 재시도가 20ms를 쓰므로 그보다 넉넉히 두고
     기다린다 — 겹친 상대도 그 사이에 자기 교체를 마친다 */
  const SAVE_RETRIES = 2;
  const SAVE_RETRY_WAIT = 150;

  const dom = {
    notice: document.getElementById('notice'),
    favicon: document.getElementById('favicon'),
    brand: document.getElementById('brand'),
    project: document.getElementById('project'),
    projectPath: document.getElementById('projectPath'),
    search: document.getElementById('search'),
    tabs: document.getElementById('tabs'),
    split: document.getElementById('split'),
    list: document.getElementById('list'),
    handle: document.getElementById('handle'),
    body: document.getElementById('bodyInner'),
    back: document.getElementById('back')
  };

  const App = {
    data: JSON.parse(document.getElementById('data').textContent),
    // 판정 방식의 근거는 읽기 전용 판정 문서가 갖는다. 셸이 먼저 필요하므로
    // 여기서 한 번 판정해 공개하고 파괴적 연산 UI는 이 값을 읽는다
    readonly: location.protocol === 'file:',
    /* 지금 살아 있는 세션 UUID. 서버가 SSE로 밀어 준다. embed에 담지 않으므로 첫
       페인트에서는 비어 있고, file://에서는 끝까지 비어 있다 — 사본은 무엇이 살아
       있는지 보증할 수 없으므로 그쪽에 표시가 없는 것이 옳다 */
    live: [],
    /* 이 창이 지금 보고 있는 세션 UUID. 서버가 SSE로 밀어 준다. **초기값이 `[]`가 아니라
       `null`인 것에 뜻이 있다** — embed에도 `current`(이 파일을 만든 세션)가 있으므로,
       아직 서버가 말하지 않은 상태와 "창이 아무 세션도 보고 있지 않다"를 갈라야 한다.
       전자면 embed 값을 쓰고 후자면 표식이 없다. file://에서는 끝까지 null이다 */
    current: null,
    /* 서버에 닿지 않는 상태. 배너 문구(`notices.offline`)와 따로 공개하는 이유는 그 문구가
       자리 하나를 두고 경합하는 값이라 「지금 끊겼는가」를 그것으로 물어볼 수 없기 때문이다.
       서버에 닿는 것을 전제하는 조작이 이 값을 읽어 자기 자리를 거둔다 */
    offline: false,
    /* 사용자 설정. 읽기는 산출물에 심긴 값이고 쓰기는 진입 경로가 가른다 —
       서버로 열었으면 `~/.claude/history/config.json`으로, 파일로 열었으면 브라우저로.
       화면은 어느 쪽인지 몰라도 된다.

       서버 진입에서 브라우저 저장을 보지 않는 이유는 오리진이 고정이 아니기 때문이다.
       후보 포트가 OS 예약에 걸리면 매 실행마다 다른 포트에 붙으므로 그 저장소는 늘 비어
       있다. 그 사정은 `20-viewer/050-user-config.md`가 갖는다 */
    config: {
      values: JSON.parse(document.getElementById('config').textContent),
      get(key) {
        if (App.readonly) {
          try {
            const stored = localStorage.getItem(CONFIG_PREFIX + key);
            if (stored !== null) return JSON.parse(stored);
          } catch (e) {
            // 접근이 막혔거나 값이 JSON이 아니다. 심긴 값으로 간다
          }
        }
        return App.config.values[key];
      },
      set(key, value) {
        App.config.values[key] = value;
        if (App.readonly) {
          try {
            localStorage.setItem(CONFIG_PREFIX + key, JSON.stringify(value));
          } catch (e) {
            // 저장하지 못해도 이번 화면은 바뀐 채로 둔다
          }
          return;
        }
        postConfig(key, value, 0);
      }
    },
    impls: {},
    provide(key, impl) { App.impls[key] = impl; },
    // 해시를 다시 읽고 탭·목록·본문을 그린다. 파괴적 연산 UI가 삭제 응답을 반영한 뒤에
    // 부른다 — 항목 수를 다시 세고 사라진 열람 대상을 정정하는 경로가 이미 여기에 있다
    refresh() { route(); },
    /* 목록만 다시 그린다. refresh()와 달리 본문을 건드리지 않는다 — 살아 있는 세션은
       사용자가 대화를 읽고 있는 도중에 뜨고 죽으므로, 본문까지 다시 그리면 그때마다
       스크롤 위치와 검색 매치 위치가 날아간다 */
    refreshList() {
      const at = dom.list.scrollTop;
      /* 검색 중에는 renderList가 impl.search로 행을 새로 만든다. 그때 impl.list()를
         부르면 축이 기억하는 질의가 비워져 본문의 매치 강조가 풀린다 */
      if (!state.query) {
        const impl = App.impls[state.axis];
        state.rows = impl ? (impl.list() || []) : [];
      }
      renderList();
      dom.list.scrollTop = at;
    }
  };
  window.App = App;

  // 열람 대상은 해시가 정한다. 검색어와 체크 선택은 여기 밖에 있고 축이 바뀌면 비워진다
  const state = { axis: 's', id: '', query: '', rows: [] };

  /* 설정 저장 요청 하나. **본문의 `ok`가 false일 때만 다시 보낸다.**

     그것은 「다른 창이 그 파일을 교체하는 중」이라는 뜻이고 그 상태는 수십 ms 안에 풀린다 —
     설정 파일은 프로젝트마다 갈리지 않아 서버 여럿이 같은 파일에 쓰기 때문이며, 사정은
     `20-viewer/050-user-config.md`가 갖는다. 서버가 이미 짧게 재시도하므로 여기까지 오는
     것은 그것마저 겹친 경우다.

     **상태코드로 판정하지 않는다.** 그쪽이면 4xx여야 하는데 브라우저가 4xx를 콘솔에 ERROR로
     남기므로, 재시도가 정상 동작인 이 경로가 매번 빨간 줄을 만든다. 서버가 200에 `ok`를
     싣는 이유가 그것이다.

     **400·403은 다시 보내지 않는다.** 요청을 고쳐야 통하는 것이라 같은 요청은 같은 답을
     받는다 — `response.ok`가 그 둘을 걸러 낸다.

     재시도 직전에 그 키의 최신 값을 다시 본다. 사용자가 빠르게 두 번 누르면 재시도가 둘
     겹치는데, 확인하지 않으면 **늦게 출발한 옛 값이 나중에 도착해 최종이 된다.**

     사용자에게 알리지 않는다. 이 경고를 띄우면 성공했는지 확인하러 한 번 더 누르게 되고,
     그 자리(`#notice`)는 연결 끊김이 쓰는 자리라 무슨 문장이든 「잘못됐다」로 읽힌다.
     끝까지 실패해도 화면을 되돌리지 않는다 — 방금 본 변화를 취소하는 것이 저장 실패보다
     놀랍고, 저장되지 않았다는 사실은 다음에 열 때 옛 값으로 드러난다 */
  function postConfig(key, value, attempt) {
    const token = new URLSearchParams(location.search).get('t') || '';
    fetch(`/api/config?t=${encodeURIComponent(token)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [key]: value })
    })
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        if (!body || body.ok !== false || attempt >= SAVE_RETRIES) return;
        setTimeout(() => {
          if (App.config.values[key] === value) postConfig(key, value, attempt + 1);
        }, SAVE_RETRY_WAIT);
      })
      .catch(() => {});
  }

  function el(tag, text, cls) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }

  function axisAt(key) {
    for (let i = 0; i < AXES.length; i++) if (AXES[i].key === key) return AXES[i];
    return null;
  }

  // ── 해시 라우팅 ──────────────────────────────────────────────────────────

  function parseHash() {
    const raw = location.hash.replace(/^#/, '');
    const slash = raw.indexOf('/');
    const key = slash < 0 ? raw : raw.slice(0, slash);
    if (!axisAt(key)) return { axis: 's', id: '' };
    const rest = slash < 0 ? '' : raw.slice(slash + 1);
    return { axis: key, id: rest ? decodeURIComponent(rest) : '' };
  }

  function hashFor(axis, id) {
    return `#${axis}/${id ? encodeURIComponent(id) : ''}`;
  }

  function goto(axis, id) {
    const next = hashFor(axis, id);
    if (location.hash === next) route();
    else location.hash = next;
  }

  function pick(rows, wanted) {
    if (!rows.length) return '';
    for (let i = 0; i < rows.length; i++) if (rows[i].id === wanted) return wanted;
    return rows[0].id;
  }

  function route() {
    const next = parseHash();
    if (next.axis !== state.axis) {
      // 축이 바뀌는 모든 경로에서 같게 동작한다 — 탭 클릭이든 뒤로가기든.
      // 비우는 것은 검색어와 체크 선택뿐이고 열람 대상은 해시가 정하므로,
      // 뒤로 간 화면에서 해시와 본문이 어긋날 자리가 없다
      state.query = '';
      dom.search.value = '';
      document.dispatchEvent(new CustomEvent('axis-change', { detail: next.axis }));
    }
    state.axis = next.axis;

    const impl = App.impls[state.axis];
    if (impl) {
      state.rows = impl.list() || [];
      state.id = pick(state.rows, next.id);
      // 해시가 가리키는 항목이 없으면 첫 항목으로 정정하고 URL도 맞춘다.
      // 히스토리에 항목을 더하지 않으려고 replaceState를 쓴다
      const canonical = hashFor(state.axis, state.id);
      if (location.hash !== canonical) {
        history.replaceState(null, '', location.pathname + location.search + canonical);
      }
    } else {
      // 구현이 꽂히지 않은 축은 "항목이 없다"가 아니라 "모른다"이다. 해시의 식별자를
      // 버리면 축이 붙기 전에 연 링크가 대상을 잃는다
      state.rows = [];
      state.id = next.id;
    }

    renderTabs();
    renderList();
    renderBody();
  }

  // ── 축 탭 ────────────────────────────────────────────────────────────────

  function renderTabs() {
    dom.tabs.textContent = '';
    AXES.forEach((axis) => {
      const button = el('button');
      // 라벨과 항목 수를 따로 담는다. 한 텍스트 노드로 두면 숫자만 흐리게 할 수 없다.
      // 보이는 문자열은 두 노드를 이은 것과 같다
      button.appendChild(el('span', axis.label));
      button.appendChild(el('span', `(${axis.count(App.data)})`, 'tab-count'));
      button.type = 'button';
      button.setAttribute('aria-selected', axis.key === state.axis ? 'true' : 'false');
      button.addEventListener('click', () => {
        // 탭을 눌렀는데 열람 대상이 비는 상태는 없다. 그 축에 항목이 하나도
        // 없을 때만 접두사만 남는다
        const impl = App.impls[axis.key];
        const rows = impl ? (impl.list() || []) : [];
        goto(axis.key, rows.length ? rows[0].id : '');
      });
      dom.tabs.appendChild(button);
    });
  }

  // ── 목록 패널 ────────────────────────────────────────────────────────────

  function renderList() {
    dom.list.textContent = '';
    const impl = App.impls[state.axis];
    if (!impl) {
      dom.list.appendChild(el('div', '이 축의 화면이 아직 붙지 않았습니다.', 'empty'));
      return;
    }
    addSlot(impl.head);
    if (state.query) {
      renderGroups(impl.search(state.query) || []);
    } else if (!state.rows.length) {
      dom.list.appendChild(el('div', '항목이 없습니다.', 'empty'));
    } else {
      state.rows.forEach(addRow);
    }
    addSlot(impl.foot);
  }

  /* 목록 패널의 머리·꼬리 슬롯. 행이 아닌 것(배너·구획)을 축이 넣는 자리다.
     검색 여부와 무관하게 그리는 이유는 그것이 걸러진 목록이 아니라 전체를 말하기
     때문이고, 클릭 리스너를 붙이지 않는 이유는 행이 아니라 열람 대상을 갖지 않기
     때문이다. 주지 않는 축도 있다 — 세션 축은 주지 않는다 */
  function addSlot(make) {
    if (!make) return;
    const node = make();
    if (node) dom.list.appendChild(node);
  }

  function renderGroups(groups) {
    let total = 0;
    groups.forEach((group) => { total += group.rows.length; });
    if (!total) {
      dom.list.appendChild(el('div', '검색 결과가 없습니다.', 'empty'));
      return;
    }
    groups.forEach((group) => {
      // 그룹이 하나뿐이고 이름이 없으면 머리를 그리지 않는다. 그룹의 수와 이름은 축이 정한다
      if (group.label) {
        dom.list.appendChild(
          el('div', `${group.label} (${group.rows.length})`, 'group-label')
        );
      }
      group.rows.forEach(addRow);
    });
  }

  function addRow(row) {
    const node = row.node;
    if (row.id === state.id) node.setAttribute('aria-current', 'true');
    node.addEventListener('click', (event) => {
      // 행 안의 체크박스·링크는 자기 동작을 갖는다
      if (event.target.closest('input, a, button')) return;
      document.body.classList.add('on-body');
      goto(state.axis, row.id);
    });
    dom.list.appendChild(node);
  }

  // ── 본문 패널 ────────────────────────────────────────────────────────────

  function renderBody() {
    dom.body.textContent = '';
    const impl = App.impls[state.axis];
    const node = impl && state.id ? impl.body(state.id) : null;
    dom.body.appendChild(node || el('div', impl ? '표시할 항목이 없습니다.'
                                                : '이 축의 화면이 아직 붙지 않았습니다.', 'empty'));
  }

  // ── 검색 ─────────────────────────────────────────────────────────────────

  function bindSearch() {
    dom.search.addEventListener('input', () => {
      // 정규화는 셸이 한다 — 앞뒤 공백을 없애고 소문자로 넘긴다.
      // 축은 자기 대상을 같은 방식으로 낮춰 비교한다
      state.query = dom.search.value.trim().toLowerCase();
      renderList();
    });
  }

  // ── 패널 폭 ──────────────────────────────────────────────────────────────

  function applyPaneWidth(px) {
    document.documentElement.style.setProperty('--pane-width', `${px}px`);
  }

  function bindHandle() {
    const stored = App.config.get('paneWidth');
    if (stored > 0) applyPaneWidth(stored);

    let dragging = false;
    dom.handle.addEventListener('pointerdown', (event) => {
      dragging = true;
      dom.handle.setPointerCapture(event.pointerId);
      dom.handle.classList.add('dragging');
      event.preventDefault();
    });
    dom.handle.addEventListener('pointermove', (event) => {
      if (!dragging) return;
      const left = dom.split.getBoundingClientRect().left;
      const max = dom.split.clientWidth * PANE_MAX_RATIO;
      const width = Math.round(Math.min(Math.max(event.clientX - left, PANE_MIN), max));
      applyPaneWidth(width);
    });
    dom.handle.addEventListener('pointerup', () => {
      if (!dragging) return;
      dragging = false;
      dom.handle.classList.remove('dragging');
      const width = parseInt(
        getComputedStyle(document.documentElement).getPropertyValue('--pane-width'), 10);
      if (width > 0) App.config.set('paneWidth', width);
    });
  }

  // ── 상단 안내 ────────────────────────────────────────────────────────────

  /* 안내는 자리가 하나뿐이라 무엇을 띄울지 정해야 한다. **끊김이 이긴다** — 서버가
     없으면 새로고침해도 목록이 늘지 않으므로, 그 상태에서 「새로고침」을 권하는 것은
     듣지 않는 처방이다. 각 사유는 자기 칸에만 쓰고 그릴 자리는 여기 하나다 */
  const notices = { offline: '', staleCount: 0 };

  /* 끊김을 아는 쪽이 셸이므로 알리는 것도 셸이다. **이벤트로 알리고 남의 DOM을 만지지
     않는다** — 여기서 `#tb-refresh`를 직접 거두면 그 식별자가 두 파일에 생겨, 툴바가 버튼을
     고칠 때 이 파일이 조용히 낡는다. 상태를 함께 두는 이유는 늦게 붙는 쪽이 이미 끊긴 뒤에
     생길 수 있어서다 — 이벤트는 그때 이미 지나갔고 `App.offline`은 남아 있다.

     **이벤트에 값을 싣지 않는다.** 받는 쪽은 `App.offline`을 읽는다. 값을 실으면 진실이 둘이
     되어, 하나를 보는 컨트롤과 다른 하나를 보는 컨트롤이 어긋난 상태로 남을 수 있다 */
  function setOffline(on) {
    if (App.offline === on) return;
    App.offline = on;
    document.dispatchEvent(new CustomEvent('app-offline'));
  }

  function renderNotice() {
    dom.notice.textContent = '';
    if (notices.offline) {
      dom.notice.appendChild(document.createTextNode(notices.offline));
    } else if (notices.staleCount > 0) {
      dom.notice.appendChild(document.createTextNode(
        `아직 목록에 없는 세션이 ${notices.staleCount}개 있습니다.`));
      const button = el('button', '새로고침', 'notice-act');
      button.type = 'button';
      // 다시 여는 것 자체가 갱신이다 — 서버가 `GET /`에서 산출물을 다시 만든다
      button.addEventListener('click', () => { location.reload(); });
      dom.notice.appendChild(button);
    } else {
      dom.notice.hidden = true;
      return;
    }
    dom.notice.hidden = false;
  }

  /* 서버가 미는 「기록이 남은 세션」과 화면이 심고 있는 목록의 차다.
     **개수만 세고 목록을 건드리지 않는다** — 데이터는 생성 시점에 embed되므로 이 자리에서
     행을 만들면 제목도 대화도 없는 껍데기가 선다. 그 행을 만들 수 있는 것은 재생성뿐이다 */
  function unseenCount(ids) {
    const have = Object.create(null);
    (App.data.sessions || []).forEach((session) => { have[session.id] = true; });
    let count = 0;
    ids.forEach((id) => { if (!have[id]) count++; });
    return count;
  }

  // ── 서버 연결 ────────────────────────────────────────────────────────────

  function connect() {
    // file://에서는 열지 않는다. 읽기 전용 판정과 같은 조건이다
    if (App.readonly) return;
    const token = new URLSearchParams(location.search).get('t') || '';
    const source = new EventSource(`/api/live?t=${encodeURIComponent(token)}`);
    let failing = null;

    source.addEventListener('open', () => {
      if (failing) { clearTimeout(failing); failing = null; }
      notices.offline = '';
      setOffline(false);
      renderNotice();
    });

    /* 세 이벤트 모두 접속 직후 한 번, 그 뒤로는 그 값이 변할 때만 온다. 따라서 이벤트가
       왔다는 것 자체가 변화다. 알아들을 수 없는 값으로 화면을 흔들지 않는다 — 파싱에
       실패하면 직전 상태를 그대로 둔다 */
    function onEvent(name, apply) {
      source.addEventListener(name, (event) => {
        let value;
        try {
          value = JSON.parse(event.data);
        } catch (error) {
          return;
        }
        apply(value);
      });
    }

    /* 형 검사는 값마다 다르다. 배열인 둘과 문자열인 하나를 한 검사로 묶으면 그 검사가
       아무것도 걸러내지 못한다 — 파싱만 공통이다 */
    function onList(name, apply) {
      onEvent(name, (value) => { if (Array.isArray(value)) apply(value); });
    }

    // 살아 있는 세션 — 행의 배지와 체크박스가 이 값을 읽는다
    onList('live', (ids) => {
      App.live = ids;
      App.refreshList();
    });
    /* 기록이 남은 세션 — 이 화면이 아직 모르는 것이 있으면 알린다.
       `live`와 갈라 두는 이유는 살아 있어도 jsonl이 없는 세션이 있기 때문이다.
       그것으로 안내를 띄우면 새로고침해도 행이 서지 않아 안내가 사라지지 않는다 */
    onList('known', (ids) => {
      notices.staleCount = unseenCount(ids);
      renderNotice();
    });
    /* 이 창이 보고 있는 세션 — `/resume`으로 갈아타면 이 값이 옮겨간다. 그래서 embed에
       굳은 값을 덮어야 하고, 빈 문자열로 덮는 것도 사실이므로 걸러내지 않는다 */
    onEvent('current', (id) => {
      if (typeof id !== 'string') return;
      App.current = id;
      App.refreshList();
    });

    // 재시도는 EventSource가 이미 한다. 이 페이지에 필요한 것은 재접속이 아니라
    // 왜 편집이 안 되는지를 알리는 것이다
    source.addEventListener('error', () => {
      if (failing) return;
      failing = setTimeout(() => {
        notices.offline = '서버와 연결이 끊겼습니다. 편집하려면 Claude Code에서 /history를 다시 실행합니다.';
        setOffline(true);
        renderNotice();
      }, DISCONNECT_GRACE);
    });
  }

  // ── 기동 ─────────────────────────────────────────────────────────────────

  /* 경로의 마지막 조각이 프로젝트 이름이다. 그것을 제목 자리에 세우고 전체 경로는 그
     뒤에 고르게 둔다 — 강조가 한 곳이어야 눈이 갈 곳이 갈리지 않는다.

     구분자는 두 종류를 함께 본다 — 값이 서버에서 오고 그쪽 OS가 무엇인지 화면은 모른다.
     구분자가 없으면(경로가 한 조각) 전체가 이름이고, 끝이 구분자로 끝나 이름이 비면
     경로만 남는다.

     경로에서 이름을 잘라내지 않는다. 그것은 **전체 경로를 확인하려는 값**이므로 한 조각이
     빠지면 그 일을 하지 못한다. 같은 낱말이 두 번 보이는 대가는 감수한다 */
  function projectName(path) {
    const at = Math.max(path.lastIndexOf('\\'), path.lastIndexOf('/'));
    return path.slice(at + 1);
  }

  function renderProject(path) {
    const name = projectName(path);
    dom.project.textContent = name;
    dom.projectPath.textContent = path;
    /* 탭이 좁아지면 뒤가 잘리므로 **이름이 앞이다.** 「history · {이름}」으로 두면 탭 줄에
       전부 `history…`로 보여 구분이 사라진다. 머리와 순서가 뒤집히는 것은 탭이 폭 제약이
       지배하는 다른 자리이기 때문이다.

       구분자는 화면 안이 쓰는 것과 같은 가운뎃점이다. em dash를 쓰지 않는다 — 긴 선이
       이름과 꼬리표를 대등한 두 항목으로 만든다. `•`(U+2022)도 쓰지 않는다: 이 화면에서
       채워진 원은 〈● 실행중〉의 것이고, 탭 글자 크기에서 둘은 크기만 다른 같은 모양이다 */
    document.title = name ? `${name} · history` : 'history';
    dom.favicon.href = faviconUrl(name, path);
  }

  /* 파비콘을 문자열로 조립하지 않는다. 이름은 폴더명이므로 `&`나 `<`가 들어갈 수 있고,
     문자열 SVG는 그 이스케이프를 잊을 수 있는 단계로 만든다 — `innerHTML`을 쓰지 않는
     것과 같은 이유다. DOM으로 만들어 `XMLSerializer`에 넘기면 이스케이프가 브라우저 몫이 된다.

     한 글자만 넣는다. 두 글자는 16px 아이콘에서 뭉개져 색만 남는다 */
  function faviconUrl(name, path) {
    const NS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('xmlns', NS);
    svg.setAttribute('viewBox', '0 0 32 32');
    // 크기를 적어 둔다. `viewBox`만 있으면 고유 크기가 SVG의 기본값(150×150)이 되고,
    // 그 값을 아이콘 크기로 쓰는 브라우저에서 한 번 더 축소된다
    svg.setAttribute('width', '32');
    svg.setAttribute('height', '32');
    const rect = document.createElementNS(NS, 'rect');
    rect.setAttribute('width', '32');
    rect.setAttribute('height', '32');
    rect.setAttribute('rx', '8');
    rect.setAttribute('fill', FAVICON_COLORS[pathHash(path) % FAVICON_COLORS.length]);
    const text = document.createElementNS(NS, 'text');
    text.setAttribute('x', '16');
    text.setAttribute('y', '17');
    text.setAttribute('fill', '#fff');
    text.setAttribute('font-family', 'system-ui, sans-serif');
    text.setAttribute('font-size', '19');
    text.setAttribute('font-weight', '600');
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('dominant-baseline', 'central');
    text.textContent = (name[0] || '?').toUpperCase();
    svg.appendChild(rect);
    svg.appendChild(text);
    return 'data:image/svg+xml,'
      + encodeURIComponent(new XMLSerializer().serializeToString(svg));
  }

  /* 이름이 아니라 **경로**를 해시한다. 이름은 이미 아이콘의 글자와 탭 제목이 말하므로,
     색까지 이름을 따르면 같은 신호가 셋이 된다. 경로를 쓰면 이름이 같고 위치가 다른
     둘(`dev\skills\clip`과 `plugins\clip`)이 색으로 갈린다 */
  function pathHash(path) {
    let hash = 0;
    for (let i = 0; i < path.length; i++) {
      hash = (hash * 31 + path.charCodeAt(i)) >>> 0;
    }
    return hash;
  }

  /* 경로는 **다 보이거나 사라진다.** 잘린 경로는 전체 경로가 아니므로 확인용으로 쓸 수 없고,
     생략 기호가 붙은 채 남으면 그것이 전체인 줄 읽힌다.

     필요한 폭은 처음 한 번만 잰다. 경로 문자열이 세션 동안 바뀌지 않으므로 다시 재도 같은
     값이고, **숨긴 뒤에는 잴 수 없다**(`display: none`의 폭은 0이다). 그래서 첫 호출이
     보이는 상태에서 일어나야 한다 — `start()`가 그 자리다.

     `hidden`을 쓰는 것은 이 화면이 `#notice`에서 이미 쓰는 방식이다 */
  let pathWidth = 0;
  let pathOffset = 0;

  function fitPath() {
    if (!pathWidth) {
      pathWidth = dom.projectPath.offsetWidth;
      /* 경로가 시작되는 x. 앞의 셋과 그 사이 간격을 합친 값이다.

         **`brand.scrollWidth`로 내용 폭을 잴 수 없다.** 이 묶음은 남는 폭을 전부 차지하므로
         내용이 그보다 작으면 그 값이 `clientWidth`와 같아지고, 그러면 판정이 늘 「넘친다」로
         답해 넓은 화면에서도 경로가 사라진다 */
      pathOffset = dom.projectPath.getBoundingClientRect().left
        - dom.brand.getBoundingClientRect().left;
    }
    dom.projectPath.hidden = pathOffset + pathWidth + PATH_MARGIN > dom.brand.clientWidth;
  }

  function start() {
    renderProject(App.data.project);
    fitPath();
    // 창 크기와 함께 판정을 다시 한다. `resize`가 아니라 요소를 보는 쪽이라, 나중에 머리에
    // 무엇이 더 붙어 폭이 달라지는 경우도 같은 경로로 잡힌다
    new ResizeObserver(fitPath).observe(dom.brand);
    dom.back.addEventListener('click', () => {
      document.body.classList.remove('on-body');
    });
    bindSearch();
    bindHandle();
    window.addEventListener('hashchange', route);
    // 축 스크립트는 파일명 순서로 이 파일보다 뒤에 오므로, 이 시점에 등록이 끝나 있다
    route();
    connect();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
