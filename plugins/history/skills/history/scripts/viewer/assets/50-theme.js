/* 테마 토글 — 시스템 · 라이트 · 다크의 순환과 저장.
 *
 * 저장된 선택을 화면에 **처음** 적용하는 것은 이 파일이 아니라 shell.html의 <head> 부트다.
 * 자산 JS는 <body> 끝에 조립되므로 여기서 처음 적용하면 이미 그려진 화면이 뒤집힌다.
 * 이 파일은 그 뒤의 순환 · 저장 · 라벨 · OS 추종을 갖는다.
 *
 * 저장 자리는 App.config가 정한다 — 서버로 열었으면 `~/.claude/history/config.json`,
 * 파일로 열었으면 브라우저다.
 *
 * App.provide로 등록하지 않는다. 축이 아니므로 그 대상이 아니고, 축을 옮기거나 검색해도
 * 테마는 그대로여야 한다.
 */
(function () {
  'use strict';

  // 순환 순서이자 저장 가능한 값의 전부다
  const ORDER = ['system', 'light', 'dark'];

  /* 아이콘은 24×24 좌표계에 그리고 버튼에서 16px로 줄인다. currentColor를 쓰므로
     테마가 뒤집혀도 글자와 같은 색을 따라간다 */
  const ICON = {
    // 자동은 글자 A다. 해와 달 사이에 낄 세 번째 천체가 없으므로 기호가 아니라 이름을 쓴다
    system: '<circle cx="12" cy="12" r="9"/>'
      + '<path d="M8.6 16 12 7.6 15.4 16M9.9 13.4h4.2" fill="none"'
      + ' stroke="var(--bg)" stroke-width="1.7" stroke-linecap="round"/>',
    light: '<circle cx="12" cy="12" r="4.2"/>'
      + '<path d="M12 2.6v2.6M12 18.8v2.6M4.34 4.34l1.84 1.84M17.82 17.82l1.84 1.84'
      + 'M2.6 12h2.6M18.8 12h2.6M4.34 19.66l1.84-1.84M17.82 6.18l1.84-1.84"'
      + ' fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>',
    // 원 하나를 다른 원으로 깎아 낸다. 채운 초승달이라 작은 크기에서 형태가 뭉개지지 않는다
    dark: '<path d="M20.5 14.4A9 9 0 1 1 9.6 3.5a7.2 7.2 0 0 0 10.9 10.9Z"/>'
  };

  /* 누르면 무엇이 되는지까지 말한다. 아이콘만으로는 세 상태 중 어디인지도,
     눌러서 어디로 가는지도 읽히지 않는다 */
  const TITLE = {
    system: '테마: 자동입니다. 누르면 라이트로 바뀝니다.',
    light: '테마: 라이트입니다. 누르면 다크로 바뀝니다.',
    dark: '테마: 다크입니다. 누르면 자동으로 바뀝니다.'
  };

  const media = matchMedia('(prefers-color-scheme: dark)');

  /* 부트와 같은 폴백을 쓴다. 둘이 갈라지면 첫 화면의 색과 버튼의 아이콘이 어긋난다 */
  function read() {
    const stored = App.config.get('theme');
    return ORDER.indexOf(stored) >= 0 ? stored : 'system';
  }

  /* 선택은 셋이고 화면은 둘이다. system은 여기서 OS 선호로 풀린다 */
  function apply(choice, button) {
    const dark = choice === 'dark' || (choice === 'system' && media.matches);
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    button.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16"'
      + ' fill="currentColor" aria-hidden="true">' + ICON[choice] + '</svg>';
    button.title = TITLE[choice];
    button.setAttribute('aria-label', TITLE[choice]);
  }

  function start() {
    const button = document.getElementById('theme');
    if (!button) return;

    let choice = read();
    apply(choice, button);

    button.addEventListener('click', () => {
      choice = ORDER[(ORDER.indexOf(choice) + 1) % ORDER.length];
      App.config.set('theme', choice);
      apply(choice, button);
    });

    /* 선택이 시스템일 때만 따라간다. 리스너를 떼지 않고 조건을 콜백 안에서 보는 것은
       등록·해제를 상태마다 관리하지 않기 위해서다. 이 콜백은 OS 설정이 바뀔 때만 불린다 */
    media.addEventListener('change', () => {
      if (choice === 'system') apply(choice, button);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
