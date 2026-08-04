/* 자체 마크다운 렌더러.
 *
 * HTML 문자열을 조립해 주입하지 않는다. DOM 노드를 만들어 붙이므로 텍스트가 마크업으로
 * 해석되는 경로 자체가 없다 — 이스케이프를 잊을 수 있는 단계를 만들지 않는 것이 목적이다.
 *
 * 블록 → 인라인 2단계다. 어느 규칙에도 걸리지 않은 문자열은 텍스트 노드로 남는다.
 * 삼켜서 사라지는 문법을 두지 않는다.
 */
(function () {
  'use strict';

  const FENCE_RE = /^(```|~~~)(.*)$/;
  const HEADING_RE = /^(#{1,6})\s+(.*)$/;
  const QUOTE_RE = /^>\s?(.*)$/;
  const LIST_RE = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
  const CELL_SEP_RE = /^\s*:?-+:?\s*$/;

  // 안전한 스킴만 링크로 만든다. `innerHTML`을 쓰지 않는 것은 태그 주입을 막지만
  // href는 별개 경로다 — `javascript:`가 담기면 클릭 한 번에 실행된다
  const SAFE_URL_RE = /^(?:https?:\/\/|mailto:|#|\/|\.{1,2}\/)/i;

  // 대안 순서가 곧 우선순위다. 인라인 코드가 가장 먼저 걸려야 그 안의 기호가
  // 마크업으로 해석되지 않는다.
  // `_`는 강조 기호로 쓰지 않는다 — 이 데이터에는 snake_case 식별자와 경로가 많아
  // 단어 안의 밑줄이 강조로 잡히면 원문이 깨진다
  const INLINE_RE = new RegExp(
    '(`+)([\\s\\S]*?)\\1' +          // 1,2  인라인 코드
    '|\\[\\[([^\\[\\]]+)\\]\\]' +    // 3    위키링크
    '|\\[([^\\]]*)\\]\\(([^()\\s]*)\\)' + // 4,5  링크
    '|(\\*\\*)([\\s\\S]+?)\\*\\*' +  // 6,7  굵게
    '|(\\*)([^*\\n]+?)\\*',          // 8,9  기울임
    'g'
  );

  function el(tag, text) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // ── 인라인 ───────────────────────────────────────────────────────────────

  function renderInline(text, wikiTargets) {
    const frag = document.createDocumentFragment();
    let last = 0;
    let match;
    // 스캐너를 호출마다 새로 만든다. 강조 안의 내용을 다시 렌더하느라 이 함수가 재귀로
    // 불리는데, 전역 정규식 하나를 공유하면 안쪽 호출이 lastIndex를 되돌려 바깥 루프가
    // 처음부터 다시 스캔한다 — 그대로 두면 `**굵게**` 하나에 무한 루프가 된다
    const scanner = new RegExp(INLINE_RE.source, 'g');
    while ((match = scanner.exec(text)) !== null) {
      if (match.index > last) {
        frag.appendChild(document.createTextNode(text.slice(last, match.index)));
      }
      frag.appendChild(inlineNode(match, wikiTargets));
      last = match.index + match[0].length;
    }
    if (last < text.length) {
      frag.appendChild(document.createTextNode(text.slice(last)));
    }
    return frag;
  }

  function inlineNode(match, wikiTargets) {
    if (match[1] !== undefined) return el('code', match[2]);
    if (match[3] !== undefined) return wikiNode(match[0], match[3], wikiTargets);
    if (match[4] !== undefined) return linkNode(match[0], match[4], match[5]);
    if (match[6] !== undefined) return withInline(el('strong'), match[7], wikiTargets);
    return withInline(el('em'), match[9], wikiTargets);
  }

  function withInline(node, text, wikiTargets) {
    node.appendChild(renderInline(text, wikiTargets));
    return node;
  }

  /* 위키링크는 옵션이다.
   *   wikiTargets === null  → 규칙이 꺼진다. 대괄호째 원문으로 남는다
   *   Set                   → 집합에 있으면 링크, 없으면 끊긴 링크
   * 빈 Set은 "규칙은 켜졌고 대상이 하나도 없다"이므로 전부 끊긴 링크가 된다. */
  function wikiNode(raw, name, wikiTargets) {
    if (!wikiTargets) return document.createTextNode(raw);
    if (wikiTargets.has(name)) {
      const link = el('a', name);
      // 해시 라우팅이 이미 hashchange를 듣고 있으므로 href만으로 이동이 성립한다.
      // 클릭 핸들러를 붙이면 같은 이동에 경로가 둘 생긴다
      link.setAttribute('href', `#m/${encodeURIComponent(name)}`);
      return link;
    }
    const broken = el('span', name);
    broken.className = 'wiki-broken';
    broken.title = '대상이 없는 링크';
    return broken;
  }

  function linkNode(raw, text, url) {
    if (!SAFE_URL_RE.test(url)) return document.createTextNode(raw);
    const link = el('a', text || url);
    link.setAttribute('href', url);
    if (/^https?:/i.test(url)) {
      link.setAttribute('target', '_blank');
      link.setAttribute('rel', 'noopener noreferrer');
    }
    return link;
  }

  // ── 블록 ─────────────────────────────────────────────────────────────────

  function isTableSep(line) {
    if (line.indexOf('|') < 0) return false;
    const cells = splitRow(line);
    return cells.length > 0 && cells.every((c) => CELL_SEP_RE.test(c));
  }

  function splitRow(line) {
    const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '');
    return trimmed.split('|');
  }

  function renderBlocks(lines, wikiTargets) {
    const frag = document.createDocumentFragment();
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];

      if (!line.trim()) { i++; continue; }

      // 코드펜스를 가장 먼저 가른다. 그 안은 어떤 인라인 처리도 받지 않는다
      const fence = FENCE_RE.exec(line);
      if (fence) {
        const mark = fence[1];
        const lang = fence[2].trim();
        const buf = [];
        i++;
        while (i < lines.length && lines[i].trim() !== mark) { buf.push(lines[i]); i++; }
        // 닫히지 않은 펜스는 파일 끝까지가 코드다
        if (i < lines.length) i++;
        frag.appendChild(codeBlock(lang, buf.join('\n')));
        continue;
      }

      const heading = HEADING_RE.exec(line);
      if (heading) {
        frag.appendChild(withInline(el(`h${heading[1].length}`), heading[2], wikiTargets));
        i++;
        continue;
      }

      if (QUOTE_RE.test(line)) {
        const quoted = [];
        while (i < lines.length && QUOTE_RE.test(lines[i])) {
          quoted.push(QUOTE_RE.exec(lines[i])[1]);
          i++;
        }
        const quote = el('blockquote');
        quote.appendChild(renderBlocks(quoted, wikiTargets));
        frag.appendChild(quote);
        continue;
      }

      if (line.indexOf('|') >= 0 && i + 1 < lines.length && isTableSep(lines[i + 1])) {
        const rows = [splitRow(line)];
        i += 2;
        while (i < lines.length && lines[i].indexOf('|') >= 0 && lines[i].trim()) {
          rows.push(splitRow(lines[i]));
          i++;
        }
        frag.appendChild(tableBlock(rows, wikiTargets));
        continue;
      }

      if (LIST_RE.test(line)) {
        const items = [];
        while (i < lines.length && LIST_RE.test(lines[i])) {
          const m = LIST_RE.exec(lines[i]);
          items.push({ indent: m[1].length, marker: m[2], text: m[3] });
          i++;
        }
        frag.appendChild(listBlock(items, wikiTargets));
        continue;
      }

      // 문단 — 다음 빈 줄이나 다른 블록이 시작될 때까지
      const para = [];
      while (i < lines.length && lines[i].trim() &&
             !FENCE_RE.test(lines[i]) && !HEADING_RE.test(lines[i]) &&
             !QUOTE_RE.test(lines[i]) && !LIST_RE.test(lines[i])) {
        para.push(lines[i]);
        i++;
      }
      if (para.length) {
        frag.appendChild(withInline(el('p'), para.join('\n'), wikiTargets));
      } else {
        i++;
      }
    }
    return frag;
  }

  function codeBlock(lang, code) {
    const pre = el('pre');
    if (lang) {
      const label = el('span', lang);
      label.className = 'lang';
      pre.appendChild(label);
    }
    pre.appendChild(el('code', code));
    return pre;
  }

  function tableBlock(rows, wikiTargets) {
    const table = el('table');
    const head = el('thead');
    head.appendChild(tableRow(rows[0], 'th', wikiTargets));
    table.appendChild(head);
    if (rows.length > 1) {
      const tbody = el('tbody');
      for (let r = 1; r < rows.length; r++) {
        tbody.appendChild(tableRow(rows[r], 'td', wikiTargets));
      }
      table.appendChild(tbody);
    }
    return table;
  }

  function tableRow(cells, tag, wikiTargets) {
    const tr = el('tr');
    for (let c = 0; c < cells.length; c++) {
      tr.appendChild(withInline(el(tag), cells[c].trim(), wikiTargets));
    }
    return tr;
  }

  function listBlock(items, wikiTargets) {
    const root = el(ordered(items[0]) ? 'ol' : 'ul');
    const stack = [{ indent: items[0].indent, el: root }];
    for (let n = 0; n < items.length; n++) {
      const item = items[n];
      while (stack.length > 1 && item.indent < stack[stack.length - 1].indent) stack.pop();
      let top = stack[stack.length - 1];
      if (item.indent > top.indent) {
        let host = top.el.lastElementChild;
        if (!host) { host = el('li'); top.el.appendChild(host); }
        const sub = el(ordered(item) ? 'ol' : 'ul');
        host.appendChild(sub);
        stack.push({ indent: item.indent, el: sub });
        top = stack[stack.length - 1];
      }
      top.el.appendChild(withInline(el('li'), item.text, wikiTargets));
    }
    return root;
  }

  function ordered(item) {
    return /\d/.test(item.marker);
  }

  /* 마크다운 텍스트를 DocumentFragment로 만든다.
   *   options.wikiTargets — 실재하는 auto-memory 이름의 Set. 없으면 규칙이 꺼진다 */
  window.renderMarkdown = (text, options) => {
    const source = text == null ? '' : String(text);
    const wikiTargets = (options && options.wikiTargets) || null;
    return renderBlocks(source.split(/\r?\n/), wikiTargets);
  };
})();
