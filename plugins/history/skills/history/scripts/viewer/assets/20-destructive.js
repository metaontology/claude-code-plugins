/* 읽기 전용 판정에 따른 파괴적 연산 UI — 배너 · 표식 · 선택 바 · 확인 창.
 *
 * 두 축(세션 삭제 · auto-memory 폐기)이 이 컴포넌트 하나를 공유한다. 확인 절차의 성질이
 * 같기 때문이다 — 복구 불가, 다중 대상, 대상 전량 나열, 개수 명시. 축마다 다른 것은
 * 항목 한 줄의 표시와 어디로 무엇을 보내는가뿐이고 그것을 register로 받는다.
 */
(function () {
  'use strict';

  /* 등록되지 않은 축에도 표식·선택 바·확인 창이 성립한다. 축 스크립트가 아직 없는
     단계에서 콘솔로 관측하기 위한 것이고, endpoint가 비어 있으므로 요청은 나가지 않는다 */
  const DEFAULTS = {
    endpoint: '',
    noun: '항목',
    action: '삭제',
    confirmVerb: '삭제',
    warning: '되돌릴 수 없습니다.',
    describe: null,
    blocked: null,
    remove: null
  };

  const specs = {};
  /* 체크 선택과 실패 사유는 페이지 안에만 있다. 수명이 몇 초인 임시 상태라
     디스크에 저장하지 않는다 */
  const chosen = [];
  let failures = {};
  let axis = 's';
  let dom = null;

  function el(tag, text, cls) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }

  function specAt(key) {
    const given = specs[key] || {};
    const merged = {};
    for (const name in DEFAULTS) {
      merged[name] = given[name] !== undefined ? given[name] : DEFAULTS[name];
    }
    return merged;
  }

  // 셸도 SSE를 열 때 같은 것을 읽지만 그 값을 공개하지 않는다. 판정과 달리 이것은
  // 파생값이 아니라 원본을 그대로 읽는 것이므로 두 곳이 어긋날 여지가 없다
  function token() {
    return new URLSearchParams(location.search).get('t') || '';
  }

  // ── DOM 조립 ─────────────────────────────────────────────────────────────

  function addBanner() {
    const node = el('div', '🔒 읽기 전용 — 편집하려면 Claude Code에서 /history를 실행합니다.');
    node.id = 'ro-banner';
    document.body.insertBefore(node, document.body.firstChild);
  }

  /* 셸의 도구 모음(`#toolbar`) 왼쪽에 들어간다. 그 단은 검색창 때문에 늘 존재하므로,
     선택이 생겨도 아래 내용이 밀리지 않는다.

     화면 아래에 두지 않는다 — 고른 것과 그것으로 할 일이 목록 위에 있어야 눈이
     찾는다. 아래 끝에 두면 목록을 다 지나쳐야 보인다. */
  function buildBar(into) {
    const bar = el('div');
    bar.id = 'dm-bar';
    bar.hidden = true;
    const count = el('span', '', 'dm-count');
    // 개수와 실행 버튼 사이다. 고른 것 바로 옆이 그것을 무르는 자리이고,
    // 실행 버튼보다 앞이라 위험한 쪽을 지나치며 누를 일이 없다
    const clear = el('button', '선택 해제', 'dm-clear');
    clear.type = 'button';
    clear.addEventListener('click', clearChosen);
    /* 클래스를 갖는 것은 다른 자산이 **그 앞에** 자기 버튼을 넣을 자리를 지목하기
       위해서다. 세션 이름 수정(`70-rename.js`)이 그 자리를 쓴다 */
    const go = el('button', '', 'dm-go');
    go.type = 'button';
    go.addEventListener('click', openConfirm);
    bar.appendChild(count);
    bar.appendChild(clear);
    bar.appendChild(go);
    const slot = document.getElementById('toolbar');
    slot.insertBefore(bar, slot.firstChild);
    into.bar = bar;
    into.count = count;
    into.go = go;
  }

  function buildConfirm(into) {
    const confirm = document.createElement('dialog');
    confirm.id = 'dm-confirm';
    const title = el('h2', '');
    const items = el('ul', undefined, 'dm-items');
    const warn = el('p', '', 'dm-warn');
    const error = el('p', '', 'dm-error');
    error.hidden = true;

    const actions = el('div', undefined, 'dm-actions');
    // 취소를 확인보다 먼저 둔다. 브라우저가 첫 포커스 가능 요소에 포커스를 주므로
    // 이 순서가 곧 "포커스는 취소에 있다"이다
    const cancel = el('button', '취소');
    cancel.type = 'button';
    cancel.addEventListener('click', () => { confirm.close(); });
    const ok = el('button', '', 'dm-danger');
    ok.type = 'button';
    ok.addEventListener('click', submit);
    actions.appendChild(cancel);
    actions.appendChild(ok);

    [title, items, warn, error, actions].forEach((node) => {
      confirm.appendChild(node);
    });
    document.body.appendChild(confirm);
    into.confirm = confirm;
    into.title = title;
    into.items = items;
    into.warn = warn;
    into.error = error;
    into.cancel = cancel;
    into.ok = ok;
  }

  // ── 표식 ─────────────────────────────────────────────────────────────────

  /* `blocked`가 사유를 돌려주면 **체크박스를 만들지 않는다.** 비활성 체크박스는 "여기
     있는데 눌리지 않는다"이고, 왜 그런지는 축이 이미 행에 표시한다(세션 축의 `현재`·
     `실행중` 배지). 사유 문자열을 여기서 다시 쓰면 같은 말이 한 행에 두 번 나온다.

     감싸는 노드는 남긴다 — 폭을 CSS가 지켜주므로 고를 수 없는 행만 제목이 왼쪽으로
     당겨지는 일이 없다. */
  function mark(key, target) {
    // 읽기 전용에서는 표식 자체가 존재하지 않는다. 축은 null이 오면 행에 아무것도
    // 넣지 않고, 모드를 다시 판정하지 않는다
    if (App.readonly) return null;

    const spec = specAt(key);
    const wrap = el('span', undefined, 'dm');

    if (spec.blocked && spec.blocked(target)) {
      unchoose(target);
    } else {
      const box = document.createElement('input');
      // 행 안의 input 클릭은 셸이 무시하므로 체크가 행 선택을 일으키지 않는다.
      // 다른 태그로 만들면 그 규칙에서 빠진다
      box.type = 'checkbox';
      box.checked = chosen.indexOf(target) >= 0;
      box.addEventListener('change', () => { toggle(key, target, box.checked); });
      wrap.appendChild(box);
    }

    // 사유를 축이 아니라 표식이 갖는다. 축에 맡기면 축마다 따로 구현되고 한쪽이
    // 빠뜨려도 화면이 성립해 버린다
    const reason = failures[target] || '';
    if (reason) wrap.appendChild(el('span', reason, 'dm-fail'));
    return wrap;
  }

  /* 고른 뒤에 고를 수 없게 된 대상을 선택에서 뺀다. 옆 창에서 세션이 시작되면 그 행은
     고를 수 없게 되는데, 남겨두면 선택 바는 "2개 선택"인데 화면의 체크박스는 하나가 된다 */
  function unchoose(target) {
    const at = chosen.indexOf(target);
    if (at < 0) return;
    chosen.splice(at, 1);
    renderBar();
  }

  /* 고른 것을 한 번에 무른다. 확인 창의 취소는 창을 연 뒤의 출구이고, 그 앞 단계에서
     선택을 되돌리려면 체크를 하나씩 다시 눌러야 하므로 여기에 출구를 둔다.

     체크박스를 직접 끄지 않는다. `chosen`을 비우고 목록을 다시 그리면 mark가 그 배열을
     보고 `checked`를 정하므로 저절로 풀리고, 이 파일이 축의 행 구조를 알지 않아도 된다.
     `App.refresh()`가 아니라 `refreshList()`인 이유는 본문을 건드리지 않기 위해서다 —
     읽고 있던 대화의 스크롤 위치가 날아간다.

     실패 사유는 비우지 않는다. 그것은 직전 시도의 결과이지 선택이 아니다 */
  function clearChosen() {
    if (!chosen.length) return;
    chosen.length = 0;
    renderBar();
    App.refreshList();
  }

  function toggle(key, target, on) {
    // 선택이 어느 축의 것인지는 표식이 안다
    axis = key;
    const at = chosen.indexOf(target);
    if (on && at < 0) chosen.push(target);
    if (!on && at >= 0) chosen.splice(at, 1);
    renderBar();
  }

  /* 선택이 바뀐 사실과 그 내용을 바깥에 알린다.

     조회 함수를 공개하는 쪽은 쓰지 않는다. 그러면 **언제 물어볼지**를 받는 쪽이 알아야
     하는데, 선택이 바뀌는 자리는 체크 토글 · unchoose · clearChosen · 축 전환 · 삭제 결과
     반영으로 다섯이다. 그 다섯이 모두 renderBar를 지나므로 여기 한 자리에서 발행된다.

     `chosen`을 그대로 넘기지 않는다. 그 배열은 이 파일이 계속 밀고 당기는 실물이라,
     받는 쪽이 붙잡아 두면 나중에 다른 값을 보게 된다 */
  function announce() {
    document.dispatchEvent(new CustomEvent('dm-select', {
      detail: { axis: axis, targets: chosen.slice() }
    }));
  }

  function renderBar() {
    if (!dom) return;
    dom.bar.hidden = chosen.length === 0;
    // 0개가 된 것도 알려야 한다. 아래 반환보다 앞에 둔다
    announce();
    if (!chosen.length) return;
    const spec = specAt(axis);
    dom.count.textContent = `☑ ${chosen.length}개 선택`;
    dom.go.textContent = `선택 항목 ${spec.action}`;
    /* 끊긴 동안 실행만 막는다. 체크와 「선택 해제」는 서버가 필요 없는 화면 상태이므로
       그대로 둔다 — 근거는 `20-viewer/010-readonly.md`의 「끊긴 동안은 실행만 막는다」다.
       매 렌더에서 다시 정하므로 끊긴 뒤에 생긴 선택 바도 막힌 채로 선다 */
    dom.go.disabled = !!App.offline;
  }

  // ── 확인 창 ──────────────────────────────────────────────────────────────

  function openConfirm() {
    if (!chosen.length) return;
    const spec = specAt(axis);
    dom.title.textContent = `${spec.noun} ${chosen.length}개를 ${spec.confirmVerb}합니다`;

    // 고른 항목이 전부 나열된다. 개수만 보여주는 확인 창은 사용자가 무엇을 고른 줄
    // 알았는지 검증할 방법을 주지 않는다
    dom.items.textContent = '';
    chosen.forEach((target) => {
      const row = el('li');
      row.appendChild(spec.describe ? spec.describe(target)
                                    : document.createTextNode(target));
      dom.items.appendChild(row);
    });

    dom.warn.textContent = spec.warning;
    dom.error.hidden = true;
    dom.ok.textContent = `${chosen.length}개 ${spec.confirmVerb}`;
    dom.ok.disabled = false;
    dom.confirm.showModal();
    // 순서에만 기대지 않는다. 구현 차이로 다른 요소가 잡히면 확인 버튼에서 Enter가 통한다
    dom.cancel.focus();
  }

  function showError(text) {
    dom.error.textContent = text;
    dom.error.hidden = false;
    dom.ok.disabled = false;
  }

  // ── 요청과 결과 반영 ─────────────────────────────────────────────────────

  function submit() {
    const spec = specAt(axis);
    if (!spec.endpoint) {
      showError('이 축의 삭제 경로가 등록되지 않았습니다.');
      return;
    }
    dom.ok.disabled = true;
    fetch(`${spec.endpoint}?t=${encodeURIComponent(token())}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ targets: chosen.slice() })
    }).then((response) => response.json().catch(() => ({}))).then((payload) => {
      const results = payload && payload.results;
      if (!Array.isArray(results)) {
        // 400의 {"error": …}도 같은 자리에 표시한다. 창을 닫으면 아무것도 지워지지
        // 않았다는 사실이 화면 어디에도 남지 않는다
        showError((payload && payload.error) || '서버가 결과를 돌려주지 않았습니다.');
        return;
      }
      apply(spec, results);
      dom.confirm.close();
    }).catch(() => {
      showError('서버에 연결할 수 없습니다. Claude Code에서 /history를 다시 실행합니다.');
    });
  }

  function apply(spec, results) {
    // 낙관적 제거를 하지 않는다. 서버가 실제로 처리한 항목만 지운다
    failures = {};
    results.forEach((result) => {
      if (result.ok) {
        if (spec.remove) spec.remove(result.target);
      } else {
        failures[result.target] = result.reason || '실패했습니다';
      }
    });
    // 성공·실패를 가리지 않고 비운다. 실패를 남기면 다음 삭제가 같은 실패를 반복한다
    chosen.length = 0;
    renderBar();
    // 셸이 항목 수를 다시 세고 사라진 열람 대상을 첫 항목으로 정정한다. 전부 실패해도
    // 부른다 — 표식에 사유를 붙이려면 행이 다시 그려져야 한다
    App.refresh();
  }

  // ── 기동 ─────────────────────────────────────────────────────────────────

  /* DOMContentLoaded를 기다리지 않는다. 인라인 <script>가 body의 마지막 자식이므로 이
     시점에 body가 이미 있고, 셸의 route()는 DOMContentLoaded에서 불리며 그 안에서 축이
     mark를 부른다 — 셸의 리스너가 이 파일의 것보다 먼저 걸리므로, 기다리면 선택 바가
     없는 상태에서 표식이 만들어진다 */
  if (App.readonly) {
    addBanner();
  } else {
    dom = {};
    buildBar(dom);
    buildConfirm(dom);
  }

  // 축이 바뀌면 체크 선택과 실패 사유를 함께 비운다. 사유는 직전 시도의 결과이고
  // 그 시도의 대상은 다른 축의 것이다. 셸이 체크 상태를 직접 만지지 않는 이유는
  // 그러면 셸이 이 파일의 DOM 구조를 알게 되기 때문이다
  document.addEventListener('axis-change', (event) => {
    axis = event.detail;
    chosen.length = 0;
    failures = {};
    renderBar();
  });

  /* 서버가 죽거나 돌아오면 실행 버튼의 가능 여부가 바뀐다. 선택은 건드리지 않는다 —
     비우면 재연결된 사용자가 고르던 것을 잃고, 그 선택은 서버와 무관한 화면 상태다 */
  document.addEventListener('app-offline', renderBar);

  window.Destructive = {
    register(key, spec) { specs[key] = spec || {}; },
    mark,
    failure(target) { return failures[target] || ''; }
  };
})();
