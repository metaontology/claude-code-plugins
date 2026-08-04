/* 도구 모음 오른쪽의 전역 동작 — 새로고침과 메뉴(설정 초기화).
 *
 * 축과 무관하다. 어느 탭을 보고 있든 같게 동작하므로 App.provide로 등록하지 않고,
 * window에 아무것도 공개하지 않는다 — 다른 자산이 이것을 부를 일이 없다.
 *
 * 아이콘은 24×24 좌표계에 그려 16px로 줄인다. currentColor를 쓰므로 테마가 뒤집혀도
 * 글자와 같은 색을 따라간다. 문자 기호(⟳ · ☰)를 쓰지 않는다 — 글꼴에 따라 크기와
 * 두께가 달라져 머리의 테마 버튼과 나란히 섰을 때 둘의 무게가 어긋난다.
 */
(function () {
  'use strict';

  // 브라우저에 남긴 설정의 키 접두사. 00-app.js의 CONFIG_PREFIX와 같은 값이다 —
  // 파일로 연 화면의 초기화가 지우는 대상이 그것이므로 같아야 한다
  const CONFIG_PREFIX = 'history.viewer.';

  /* 새로고침은 **반원 둘이 서로를 뒤따르는 순환**이다. 각 호는 원(중심 12,12 · 반지름 7)의
     12시·6시에서 시작해 시계방향으로 돌고, 끝에 채운 삼각형이 붙는다.

     한 바퀴 원호에 갈고리를 붙이는 쪽은 쓰지 않는다. 갈고리의 방향과 원호의 진행 방향이
     눈에 어긋나 **글자 G로 읽힌다**(실물 관측).

     삼각형은 호 끝의 **접선 방향**에 맞춘다. 축(수평·수직)에 맞추면 화살촉이 원 안쪽을
     향해 원을 찌르는 것처럼 보인다 — 그쪽도 관측해 보고 버린 형태다. 두 화살표는 중심에
     대한 180° 회전 대칭이므로 좌표도 `(x, y) → (24−x, 24−y)`로 대응한다. */
  const ICON = {
    refresh: '<path d="M12 5A7 7 0 0 1 17.95 15.95" fill="none" stroke="currentColor"'
      + ' stroke-width="2" stroke-linecap="round"/>'
      + '<path d="M20.28 16.78L16.28 14.12L15.73 19.28Z" fill="currentColor"/>'
      + '<path d="M12 19A7 7 0 0 1 6.05 8.05" fill="none" stroke="currentColor"'
      + ' stroke-width="2" stroke-linecap="round"/>'
      + '<path d="M3.72 7.22L7.72 9.88L8.27 4.72Z" fill="currentColor"/>',
    menu: '<path d="M4.5 7.5h15M4.5 12h15M4.5 16.5h15" fill="none" stroke="currentColor"'
      + ' stroke-width="1.9" stroke-linecap="round"/>'
  };

  function el(tag, text, cls) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }

  function iconButton(id, name, label) {
    const button = el('button');
    button.id = id;
    button.type = 'button';
    button.className = 'tb-icon';
    button.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16"'
      + ' fill="none" aria-hidden="true">' + ICON[name] + '</svg>';
    button.title = label;
    button.setAttribute('aria-label', label);
    return button;
  }

  function token() {
    return new URLSearchParams(location.search).get('t') || '';
  }

  // ── 새로고침 ─────────────────────────────────────────────────────────────

  /* 서버가 `GET /`을 서빙하기 전에 갱신 판정을 하므로 화면이 할 일은 다시 여는 것뿐이다.
     전용 엔드포인트를 부르지 않는다 — 최신을 얻는 경로가 둘이 되면 한쪽만 고쳐진다.

     파일로 연 화면에는 만들지 않는다. 산출물 파일 자체를 열었으므로 다시 읽어도 같은
     내용이고, 눌러도 아무 일이 없는 버튼은 고장으로 읽힌다.

     **서버가 죽으면 거둔다.** 같은 이유가 더 세게 걸리는 자리다 — 그때 누르면 아무 일이
     없는 정도가 아니라 죽은 오리진을 다시 열어 **보고 있던 산출물까지 브라우저의 연결 오류
     화면으로 바뀐다.** 배너가 끊긴 동안 「새로고침」을 권하지 않는 것과 같은 규칙이며 그쪽
     근거는 `20-viewer/000-embed.md`의 「안내 자리는 하나이고 끊김이 이긴다」가 갖는다.

     자리를 비활성으로 남기지 않는다. 이 화면에 비활성 컨트롤이 하나도 없어 그 서식을
     이 버튼 하나 때문에 만들게 된다 */
  function addRefresh(into) {
    if (App.readonly) return;
    const button = iconButton('tb-refresh', 'refresh',
      '기록을 새로 읽어 화면을 갱신합니다.');
    button.addEventListener('click', () => { location.reload(); });
    /* 이미 끊긴 뒤에 만들어질 수도 있으므로 상태를 먼저 읽고, 그 뒤의 변화는 이벤트로 받는다.
       **이벤트는 「바뀌었다」는 신호일 뿐이고 값은 언제나 `App.offline`에서 읽는다** */
    const sync = () => { button.hidden = !!App.offline; };
    sync();
    document.addEventListener('app-offline', sync);
    into.appendChild(button);
  }

  // ── 메뉴 ─────────────────────────────────────────────────────────────────

  /* 항목이 하나뿐인데 메뉴를 두는 것은, 이 자리가 "축과 무관한 전역 동작"의 자리이고
     그것이 늘어날 자리이기 때문이다. 버튼으로 직접 노출하면 되돌릴 수 없는 일이
     한 번의 오클릭에 실행된다 */
  function addMenu(into) {
    const button = iconButton('tb-menu', 'menu', '메뉴를 엽니다.');
    button.setAttribute('aria-haspopup', 'true');
    button.setAttribute('aria-expanded', 'false');

    const menu = el('div');
    menu.id = 'tb-menu-pop';
    menu.hidden = true;
    menu.setAttribute('role', 'menu');

    function open() {
      menu.hidden = false;
      button.setAttribute('aria-expanded', 'true');
      reset.focus();
    }

    function close() {
      menu.hidden = true;
      button.setAttribute('aria-expanded', 'false');
    }

    const reset = el('button', '설정 초기화');
    reset.type = 'button';
    reset.setAttribute('role', 'menuitem');
    reset.addEventListener('click', () => {
      close();
      openConfirm();
    });
    menu.appendChild(reset);

    button.addEventListener('click', (event) => {
      // 이 클릭이 아래 document 리스너까지 올라가면 방금 연 메뉴가 곧 닫힌다
      event.stopPropagation();
      if (menu.hidden) open();
      else close();
    });

    /* 바깥을 누르거나 Esc를 누르면 닫힌다. 열어 둔 메뉴를 닫는 방법이 같은 버튼을 다시
       누르는 것뿐이면, 다른 곳을 눌렀을 때 메뉴가 화면에 남는다 */
    document.addEventListener('click', (event) => {
      if (!menu.hidden && !menu.contains(event.target)) close();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !menu.hidden) {
        close();
        button.focus();
      }
    });

    const wrap = el('div', undefined, 'tb-menu-wrap');
    wrap.appendChild(button);
    wrap.appendChild(menu);
    into.appendChild(wrap);
  }

  // ── 설정 초기화 ──────────────────────────────────────────────────────────

  let confirmDom = null;

  /* 파괴적 연산 UI의 확인 창(`#dm-confirm`)을 재사용하지 않는다. 그쪽은 고른 대상을
     나열하고 결과를 목록에 반영하는 구조라 대상이 없는 이 동작과 맞지 않는다.
     **모양은 20-destructive.css의 서식을 함께 써서 갈라지지 않게 한다** */
  function buildConfirm() {
    const confirm = document.createElement('dialog');
    confirm.id = 'tb-confirm';
    confirm.appendChild(el('h2', '설정을 초기화합니다'));
    confirm.appendChild(el('p', '테마와 패널 폭이 기본값으로 돌아갑니다. '
      + '되돌릴 수 없습니다.', 'dm-warn'));
    const error = el('p', '', 'dm-error');
    error.hidden = true;
    confirm.appendChild(error);

    const actions = el('div', undefined, 'dm-actions');
    // 취소를 먼저 둔다. 브라우저가 첫 포커스 가능 요소에 포커스를 주므로
    // 이 순서가 곧 "포커스는 취소에 있다"이다
    const cancel = el('button', '취소');
    cancel.type = 'button';
    cancel.addEventListener('click', () => { confirm.close(); });
    const ok = el('button', '초기화', 'dm-danger');
    ok.type = 'button';
    ok.addEventListener('click', submit);
    actions.appendChild(cancel);
    actions.appendChild(ok);
    confirm.appendChild(actions);

    document.body.appendChild(confirm);
    confirmDom = { confirm: confirm, error: error, cancel: cancel, ok: ok };
  }

  function openConfirm() {
    if (!confirmDom) buildConfirm();
    confirmDom.error.hidden = true;
    confirmDom.ok.disabled = false;
    confirmDom.confirm.showModal();
    // 순서에만 기대지 않는다. 구현 차이로 다른 요소가 잡히면 초기화에서 Enter가 통한다
    confirmDom.cancel.focus();
  }

  function showError(text) {
    confirmDom.error.textContent = text;
    confirmDom.error.hidden = false;
    confirmDom.ok.disabled = false;
  }

  /* 지우는 자리가 진입 경로마다 다르다 — 서버로 열었으면 설정 파일, 파일로 열었으면
     브라우저다. App.config가 쓰기 자리를 가르는 것과 같은 판정이다.

     성공하면 다시 연다. 심긴 값을 화면에서 되돌리려면 테마 부트까지 다시 실행돼야
     하는데 그것은 <head>에 있다 */
  function submit() {
    if (App.readonly) {
      try {
        Object.keys(localStorage)
          .filter((key) => key.indexOf(CONFIG_PREFIX) === 0)
          .forEach((key) => { localStorage.removeItem(key); });
      } catch (e) {
        showError('브라우저 저장소에 접근할 수 없습니다.');
        return;
      }
      location.reload();
      return;
    }

    confirmDom.ok.disabled = true;
    fetch(`/api/config/reset?t=${encodeURIComponent(token())}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}'
    }).then((response) => {
      if (!response.ok) throw new Error('reset failed');
      location.reload();
    }).catch(() => {
      showError('서버에 연결할 수 없습니다. Claude Code에서 /history를 다시 실행합니다.');
    });
  }

  // ── 기동 ─────────────────────────────────────────────────────────────────

  function start() {
    const slot = document.getElementById('tb-actions');
    if (!slot) return;
    addRefresh(slot);
    addMenu(slot);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
