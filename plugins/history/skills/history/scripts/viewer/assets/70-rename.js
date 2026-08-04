/* 세션 이름 수정 — 선택 바의 버튼 하나와 그것이 여는 창.
 *
 * 파괴적 연산 UI(20-destructive.js)에 얹지 않는다. 그 컴포넌트의 전제는 「복구 불가 ·
 * 다중 대상 · 대상 전량 나열 · 개수 명시」이고 그 넷이 확인 창의 구조를 정한다. 이름
 * 수정은 되돌릴 수 있고 대상이 하나이며 나열할 것이 없다 — 그 구조의 어느 자리에도
 * 들어가지 않는다. 서식만 그쪽에서 물려받는다.
 *
 * 번호가 70인 것은 App과 Destructive가 정의된 뒤에 실행돼야 하기 때문이다. 자산은
 * 파일명 순서로 이어붙으므로 그 순서가 곧 로드 순서다.
 */
(function () {
  'use strict';

  const ENDPOINT = '/api/sessions/rename';
  // 세션 축의 키. 이 축에서만 버튼이 선다
  const AXIS = 's';

  let button = null;
  /* 창은 처음 열 때 만든다. 대부분의 세션에서 한 번도 열리지 않는 창이므로, 기동에서
     만들면 모든 화면이 쓰지 않는 DOM을 갖는다 */
  let dom = null;
  // 지금 고른 세션. dm-select가 갱신하고, 비어 있으면 창이 열리지 않는다
  let target = '';

  function el(tag, text, cls) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }

  // 파괴적 연산 UI가 같은 것을 읽는다. 원본을 그대로 읽으므로 두 곳이 어긋날 여지가 없다
  function token() {
    return new URLSearchParams(location.search).get('t') || '';
  }

  /* 세션 값을 30-session.js에 묻지 않는다. 그쪽은 App.provide로 화면 셋만 꽂고 아무것도
     window에 노출하지 않으며, App.data는 셸이 공개한 값이라 어느 자산이든 읽는다.
     이 파일 하나를 위해 축의 공개 면을 늘리는 것보다 싸다 */
  function findSession(id) {
    const all = (App.data && App.data.sessions) || [];
    for (let i = 0; i < all.length; i++) if (all[i].id === id) return all[i];
    return null;
  }

  // ── 버튼 ─────────────────────────────────────────────────────────────────

  /* 「선택 해제」와 「선택 항목 삭제」 사이다. 무르는 것과 실행하는 것 사이가 곧 그 대상을
     고치는 자리이고, 위험한 쪽보다 앞이라 지나치며 누를 일이 없다 */
  function addButton() {
    button = el('button', '세션명 수정', 'rn-open');
    button.type = 'button';
    button.hidden = true;
    button.addEventListener('click', open);
    const bar = document.getElementById('dm-bar');
    bar.insertBefore(button, bar.querySelector('.dm-go'));
  }

  // ── 창 ───────────────────────────────────────────────────────────────────

  function buildDialog() {
    const dialog = document.createElement('dialog');
    dialog.id = 'rn-dialog';

    const now = el('p', '', 'rn-now');
    const input = el('input', undefined, 'rn-input');
    input.type = 'text';
    /* maxLength를 주지 않는다. 붙여넣은 이름이 말없이 잘리는 것보다 서버가 사유를
       돌려주는 편이 낫다 — 잘린 이름은 저장에 성공해 버린다 */

    const error = el('p', '', 'dm-error');
    error.hidden = true;

    const actions = el('div', undefined, 'dm-actions');
    const cancel = el('button', '취소');
    cancel.type = 'button';
    cancel.addEventListener('click', () => { dialog.close(); });
    const save = el('button', '저장');
    save.type = 'button';
    save.addEventListener('click', submit);
    actions.appendChild(cancel);
    actions.appendChild(save);

    /* Enter로 저장한다. <form method="dialog">를 쓰지 않는다 — 그쪽은 Enter가 곧 창을
       닫는 동작이라 서버의 답을 기다리며 사유를 보여줄 자리가 없다 */
    input.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      submit();
    });

    [el('h2', '세션 이름을 수정합니다'), now, input, error, actions]
      .forEach((node) => { dialog.appendChild(node); });
    document.body.appendChild(dialog);
    dom = { dialog: dialog, now: now, input: input, error: error, save: save };
  }

  function open() {
    if (!target) return;
    if (!dom) buildDialog();

    const session = findSession(target);
    const title = (session && session.title) || '';
    // 라벨은 목록 행의 것과 같다. 이름이 없는 세션에서 이 줄이 사라지면 무엇을 고치는
    // 중인지가 흐려진다
    dom.now.textContent = `현재: ${title || '(제목 없음)'}`;
    dom.input.value = title;
    dom.error.hidden = true;
    dom.save.disabled = false;
    dom.dialog.showModal();
    /* 포커스는 입력칸이다. 이 창을 여는 목적이 곧 이름을 고치는 것이므로, 확인 창처럼
       취소에 두면 매번 Tab을 한 번 더 눌러야 한다. 전체 선택해 두면 통째로 바꾸는 흔한
       경우에 지우는 동작이 필요 없다 */
    dom.input.focus();
    dom.input.select();
  }

  function showError(text) {
    dom.error.textContent = text;
    dom.error.hidden = false;
    dom.save.disabled = false;
  }

  // ── 요청과 결과 반영 ─────────────────────────────────────────────────────

  function submit() {
    dom.save.disabled = true;
    // 응답이 오는 사이에 선택이 바뀔 수 있다. 보낸 대상을 붙잡아 둔다
    const id = target;
    fetch(`${ENDPOINT}?t=${encodeURIComponent(token())}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target: id, title: dom.input.value })
    }).then((response) => response.json().catch(() => ({}))).then((payload) => {
      if (!payload || !payload.ok) {
        /* 창을 닫지 않는다. 입력한 이름이 남아 있어야 고쳐서 다시 누른다 —
           닫으면 사용자가 처음부터 다시 친다 */
        showError((payload && payload.error) || '서버가 결과를 돌려주지 않았습니다.');
        return;
      }
      apply(id, payload.title);
      dom.dialog.close();
    }).catch(() => {
      showError('서버에 연결할 수 없습니다. Claude Code에서 /history를 다시 실행합니다.');
    });
  }

  /* 응답이 돌려준 **정규화된 이름**을 쓴다. 입력칸의 값을 그대로 넣으면 앞뒤 공백이 잘린
     서버의 값과 화면이 어긋나고, 다음 새로고침에서 제목이 슬쩍 바뀐다.

     App.refresh()는 목록과 본문을 함께 다시 그린다. 제목은 목록 행(srow-title)과 대화
     머리(shead-title) 둘에 있으므로, 목록만 그리면 열려 있는 대화의 머리가 낡는다.

     선택을 풀지 않는다. 파괴적 연산 UI가 고른 것을 그대로 갖고 있고 다시 그릴 때 체크를
     복원하므로, 이어서 지우려는 동선이 끊기지 않는다 */
  function apply(id, title) {
    const session = findSession(id);
    if (session) session.title = title;
    App.refresh();
  }

  // ── 기동 ─────────────────────────────────────────────────────────────────

  // 읽기 전용에는 선택 바 자체가 없다. 버튼을 넣을 자리가 없으므로 아무것도 하지 않는다
  if (App.readonly) return;

  addButton();

  document.addEventListener('dm-select', (event) => {
    const detail = event.detail || {};
    const targets = detail.targets || [];
    /* **대상이 하나여야 한다.** 이름은 대상마다 다른 값이므로 여럿에 같은 것을 붙이는
       연산이 성립하지 않는다. 축도 함께 본다 — auto-memory 항목에는 고칠 이름이 없다 */
    const one = detail.axis === AXIS && targets.length === 1;
    target = one ? targets[0] : '';
    button.hidden = !one;
    syncOffline();
  });

  /* 이름을 고치는 것도 서버에 닿아야 하므로 끊긴 동안 막는다. 숨기지 않고 막는 이유와
     체크박스를 그대로 두는 이유는 `20-viewer/010-readonly.md`의 「끊긴 동안은 실행만
     막는다」가 갖는다. `dm-select`에서도 부르는 것은 끊긴 뒤에 처음 선택한 경우 때문이다 */
  function syncOffline() {
    button.disabled = !!App.offline;
  }

  document.addEventListener('app-offline', syncOffline);
  syncOffline();
})();
