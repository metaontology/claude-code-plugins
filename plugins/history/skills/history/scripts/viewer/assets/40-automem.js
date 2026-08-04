/* auto-memory 축 화면 — 목록 · 본문 · 검색 · 불일치 표시 · 폐기.
 *
 * 셸에 꽂는 것은 App.provide('m', {list, search, body, head, foot}) 하나이고, 폐기 계약은
 * Destructive.register('m', …)로 따로 등록한다. 아무것도 window에 노출하지 않는다.
 *
 * 해시의 id는 항목 이름이고 폐기 대상은 항목 파일명이다. 두 값이 다른 것이 이 축에만
 * 있는 성질이므로 세션 축을 따라 쓰면 그대로 틀린다.
 */
(function () {
  'use strict';

  // 메모리 규약이 못박은 네 값. 그 밖은 오타거나 옛 형식이므로 사람이 봐야 한다
  const TYPES = ['user', 'feedback', 'project', 'reference'];

  // 본문·인덱스 줄 인용 조각에서 매치 앞뒤로 남기는 글자 수
  const LEAD = 20;
  const TRAIL = 24;

  function el(tag, text, cls) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }

  // ── 조회 ─────────────────────────────────────────────────────────────────
  /* 모델이 이미 계산한 불일치를 화면에서 다시 구하지 않는다. 두 벌이 되면 어긋난다 */

  function memory() {
    return App.data.memory || {};
  }

  function items() {
    return memory().items || [];
  }

  /* 조회가 둘이다. 해시가 이름을 담고 폐기가 파일명을 담으므로 들어오는 값이 자리마다
     다르다 — 세션 축의 findSession 하나에 대응하는 자리다 */
  function findByName(name) {
    const all = items();
    for (let i = 0; i < all.length; i++) if (all[i].name === name) return all[i];
    return null;
  }

  function findByFile(file) {
    const all = items();
    for (let i = 0; i < all.length; i++) if (all[i].file === file) return all[i];
    return null;
  }

  // 끊긴 포인터는 항목이 없으므로 줄을 broken에서 찾는다
  function brokenLine(file) {
    const all = memory().broken || [];
    for (let i = 0; i < all.length; i++) if (all[i].target === file) return all[i].line;
    return '';
  }

  // ── 유형과 마커 ──────────────────────────────────────────────────────────

  function typeOk(item) {
    return TYPES.indexOf(item.type) >= 0;
  }

  /* 빈 문자열만 보지 않고 네 값과 대조한다. 앵커 없는 정규식이 유형을 `memory`로 읽던
     실물 피해가 그 형태였고, 그 값은 비어 있지 않아 빈 검사로는 걸리지 않는다 */
  function warnings(item) {
    const why = [];
    if (!typeOk(item)) why.push(`유형이 ${TYPES.join('·')} 중 하나가 아닙니다`);
    if (!item.index_line) why.push('인덱스에 이 항목을 가리키는 줄이 없습니다');
    return why;
  }

  function warnNode(why) {
    const node = el('span', '⚠', 'arow-warn');
    node.title = why.join(' · ');
    return node;
  }

  // ── 목록 행 ──────────────────────────────────────────────────────────────

  /* 호출마다 노드를 새로 만든다. 셸의 addRow가 클릭 리스너를 붙이고 aria-current를
     세우는데 지우는 코드가 없으므로, 캐시하면 리스너가 겹쳐 붙고 한 번 현재였던 행이
     영원히 현재로 남는다. 표식도 같은 이유로 매번 새로 받는다 — 실패 사유가 그 안에 있다 */
  function rowNode(item, reason) {
    const row = el('div', undefined, 'arow');

    const head = el('div', undefined, 'arow-head');
    // 폐기 대상은 이름이 아니라 파일명이다
    const badge = Destructive.mark('m', item.file);
    if (badge) head.appendChild(badge);
    const why = warnings(item);
    if (why.length) head.appendChild(warnNode(why));
    head.appendChild(el('span', item.name, 'arow-name'));
    row.appendChild(head);

    const meta = el('div', undefined, 'arow-meta');
    meta.appendChild(el('span', typeOk(item) ? item.type : '?', 'arow-type'));
    if (item.description) meta.appendChild(el('span', item.description, 'arow-desc'));
    row.appendChild(meta);

    if (reason) row.appendChild(reason);
    return row;
  }

  function list() {
    return items().map((item) => ({ id: item.name, node: rowNode(item) }));
  }

  // ── 목록 패널의 슬롯 ─────────────────────────────────────────────────────
  /* 배너와 인덱스 구획은 항목 행이 아니다. 셸이 축에게서 받는 것은 행뿐이므로
     00-app.js에 머리·꼬리 슬롯을 더해 이 자리를 만들었다 */

  function head() {
    const broken = (memory().broken || []).length;
    const missing = (memory().missing || []).length;
    if (!broken && !missing) return null;
    const node = el('div', undefined, 'am-banner');
    node.appendChild(el('span', `⚠ 불일치 ${broken + missing}건`));
    node.appendChild(el('span',
      `끊긴 포인터 ${broken} · 누락된 포인터 ${missing}`, 'am-banner-detail'));
    return node;
  }

  function foot() {
    const wrap = el('div', undefined, 'am-index');
    wrap.appendChild(el('div', '인덱스', 'am-index-head'));

    // MEMORY.md는 지금이든 나중이든 지울 대상이 아니므로 회색 체크박스도 두지 않는다
    const file = el('div', undefined, 'am-index-file');
    file.appendChild(el('span', 'MEMORY.md'));
    file.appendChild(el('span', `${(memory().index_lines || []).length}줄`,
                        'am-index-count'));
    wrap.appendChild(file);

    // 끊긴 줄에는 체크박스가 있다. 그 줄은 지울 대상이고, 항목 행이 없으므로
    // 여기가 그 줄을 지우는 유일한 화면 경로다
    (memory().broken || []).forEach((entry) => {
      const row = el('div', undefined, 'am-broken');
      const badge = Destructive.mark('m', entry.target);
      if (badge) row.appendChild(badge);
      const mark = el('span', '⚠', 'arow-warn');
      mark.title = '가리키는 항목 파일이 없습니다';
      row.appendChild(mark);
      row.appendChild(el('span', entry.line, 'am-index-line'));
      wrap.appendChild(row);
    });
    return wrap;
  }

  // ── 검색 ─────────────────────────────────────────────────────────────────
  /* 질의는 셸이 이미 앞뒤 공백을 없애고 소문자로 만들어 넘긴다 */

  function matches(text, needle) {
    return String(text || '').toLowerCase().indexOf(needle) >= 0;
  }

  function excerpt(text, needle) {
    const value = String(text || '');
    const at = value.toLowerCase().indexOf(needle);
    if (at < 0) return '';
    const from = Math.max(0, at - LEAD);
    const to = Math.min(value.length, at + needle.length + TRAIL);
    const piece = value.slice(from, to).replace(/\s+/g, ' ').trim();
    return (from > 0 ? '…' : '') + piece + (to < value.length ? '…' : '');
  }

  /* 이름·유형·설명은 행에 이미 보이므로 이유를 붙이지 않는다. 답이 필요한 것은
     보이지 않는 자리에서 걸린 경우뿐이다 — 인덱스 줄과 본문 */
  function classify(item, needle) {
    if (matches(item.name, needle) || matches(item.type, needle)
        || matches(item.description, needle)) {
      return { reason: null };
    }
    if (matches(item.index_line, needle)) {
      return { reason: el('div', `🔗 ${excerpt(item.index_line, needle)}`, 'arow-why') };
    }
    if (matches(item.body, needle)) {
      return { reason: el('div', `💬 "${excerpt(item.body, needle)}"`, 'arow-why') };
    }
    return null;
  }

  /* 그룹으로 나누지 않는다. 항목 하나가 짧아 어느 자리에서 걸렸는지가 결과의 신뢰도를
     가르지 않고, 항목이 수십 개라 매치 0인 그룹의 머리가 결과보다 많아진다.
     셸은 label이 빈 그룹의 머리를 그리지 않으므로 하나만 돌려주면 단순 필터가 된다 */
  function search(raw) {
    const needle = raw || '';
    const rows = [];
    if (needle) {
      items().forEach((item) => {
        const hit = classify(item, needle);
        if (hit) rows.push({ id: item.name, node: rowNode(item, hit.reason) });
      });
    }
    return [{ label: '', rows }];
  }

  // ── 본문 ─────────────────────────────────────────────────────────────────

  /* 집합은 본문을 그릴 때마다 새로 만든다. 폐기로 항목이 사라지므로 한 번 만들어 두면
     지워진 항목을 가리키는 링크가 계속 살아 있는 것으로 보인다 */
  function wikiTargets() {
    return new Set(items().map((item) => item.name));
  }

  function header(item) {
    const head = el('div', undefined, 'ahead');
    head.appendChild(el('div', item.name, 'ahead-name'));
    const line = el('div', undefined, 'ahead-meta');
    line.appendChild(el('span', typeOk(item) ? item.type : '?'));
    // 경로는 절단하지 않는다. 좁은 패널에서는 줄바꿈으로 흐른다
    line.appendChild(el('span', item.path, 'ahead-path'));
    head.appendChild(line);
    return head;
  }

  /* 폐기가 두 곳을 고치는 연산이므로 두 곳을 보여준 뒤에 묻는다 */
  function indexSection(item) {
    const wrap = el('div', undefined, 'am-line');
    wrap.appendChild(el('div', '인덱스 줄', 'am-line-head'));
    if (item.index_line) {
      wrap.appendChild(el('div', item.index_line, 'am-index-line'));
    } else {
      wrap.appendChild(el('div', '인덱스에 이 항목을 가리키는 줄이 없습니다.', 'am-line-none'));
    }
    return wrap;
  }

  function body(name) {
    const item = findByName(name);
    if (!item) return null;

    const wrap = el('div', undefined, 'abody');
    wrap.appendChild(header(item));

    // 본문은 절단하지 않는다. 모델이 절단하지 않은 값을 주므로 화면이 다시 자를 이유가 없다
    const text = el('div', undefined, 'md');
    text.appendChild(renderMarkdown(item.body, { wikiTargets: wikiTargets() }));
    wrap.appendChild(text);

    wrap.appendChild(indexSection(item));
    return wrap;
  }

  // ── 등록 ─────────────────────────────────────────────────────────────────

  App.provide('m', { list, search, body, head, foot });

  Destructive.register('m', {
    endpoint: '/api/auto-memory/discard',
    noun: 'auto-memory 항목',
    action: '폐기',
    // 「폐기」가 이미 되돌릴 수 없음을 말한다. 세션 축이 두 동사를 가른 것은
    // 「삭제」만으로는 휴지통으로 읽히기 때문이고, 여기에는 그 오해가 없다
    confirmVerb: '폐기',
    warning: '항목 파일과 인덱스 줄이 지워집니다. 되돌릴 수 없습니다.',
    describe(file) {
      const item = findByFile(file);
      const wrap = el('span', undefined, 'am-conf');
      wrap.appendChild(el('span', item ? item.path : file, 'am-conf-path'));
      const line = item ? item.index_line : brokenLine(file);
      wrap.appendChild(el('span', line || '(인덱스 줄 없음)', 'am-conf-line'));
      return wrap;
    },
    // blocked를 등록하지 않는다. 고를 수 없는 대상이 없고, MEMORY.md는 표식을 아예
    // 만들지 않으므로 비활성이 아니라 부재다
    remove(file) {
      const m = memory();
      const item = findByFile(file);
      const line = item ? item.index_line : brokenLine(file);
      m.items = items().filter((each) => each.file !== file);
      /* 인덱스 줄도 함께 지운다. 항목만 지우면 인덱스 구획에 이미 사라진 줄이 남아,
         폐기가 고치려던 상태를 화면이 다시 만든다. index_lines에는 파일명 키가 없으므로
         줄 문자열로 거른다 — 파일명이 다르면 줄도 다르다 */
      if (line) {
        m.index_lines = (m.index_lines || []).filter((each) => each !== line);
      }
      // 배너의 수가 이 둘의 합이므로 함께 지우지 않으면 폐기 뒤에도 수가 그대로다
      m.broken = (m.broken || []).filter((each) => each.target !== file);
      m.missing = (m.missing || []).filter((each) => each !== file);
    }
  });
})();
