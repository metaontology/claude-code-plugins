---
name: repo-scanner
description: GitHub 레포지터리를 deepwiki.com에서 분석하고 HTML 치트시트, PNG 스크린샷, Markdown 요약 파일을 export/ 폴더에 생성한다. `/repo-scanner <github-url>` 형태로 호출한다. 사용자가 GitHub 레포를 분석하거나, 레포 개요를 뽑아달라고 하거나, 특정 오픈소스 라이브러리/프로젝트를 빠르게 파악하고 싶을 때 반드시 이 스킬을 사용한다.
---

## 목적

사용자가 GitHub URL을 주면, deepwiki.com에서 해당 레포 정보를 수집해 세 가지 산출물을 만든다:

1. `export/{title}-overview.html` — TL;DR 섹션이 포함된 HTML 치트시트
2. `export/{title}-overview.png` — 위 HTML을 Playwright로 스크린샷
3. `export/{title}-overview.md` — h2 섹션으로 정리된 Markdown 요약

`{title}`은 레포명 기반의 kebab-case 문자열이다 (예: `facebook-react`, `vercel-next-js`).

---

## 단계별 실행 순서

### 1. URL 파싱 및 title 결정

`$ARGUMENTS`에서 GitHub URL을 읽는다.

- URL 예시: `https://github.com/owner/repo`
- `{title}` = `{owner}-{repo}` (소문자, 특수문자는 `-`로 치환)
- `export/` 디렉토리가 없으면 생성한다.

### 2. deepwiki.com 탐색 (Playwright)

deepwiki.com은 GitHub 레포의 위키/문서를 자동 생성해주는 사이트다. 여기서 풍부한 설명을 가져올 수 있다.

탐색 순서:
1. `https://deepwiki.com/{owner}/{repo}` 로 직접 이동
2. 페이지가 로드되면 사이드바 메뉴 항목들과 메인 콘텐츠를 수집한다
3. 사이드바에 여러 섹션이 있다면 각 섹션을 순서대로 방문해서 내용을 수집한다
4. 수집 목표: 레포 목적, 주요 기능, 아키텍처, API/설정 방법, 사용 예시 등

수집된 내용이 빈약하거나 페이지가 없을 경우, GitHub 레포 페이지(`https://github.com/{owner}/{repo}`)의 README와 메타정보도 함께 참고한다.

### 3. HTML 치트시트 생성

수집한 내용을 바탕으로 `export/{title}-overview.html`을 생성한다.

HTML 레이아웃: **칸반보드 형식 (2차원 매트릭스)**

전체 본문 콘텐츠를 칸반보드처럼 카드 그리드로 배치한다. 수집한 정보를 주제별로 카드로 나누고, CSS `display: grid`로 2차원 매트릭스 형태로 정렬한다.

**그리드 구성 방식:**
- 카드 개수와 행×열 비율은 레포 내용의 양에 따라 직접 판단한다. 정보가 적으면 2×3, 풍부하면 3×4나 4×4 등으로 조정한다.
- 중요하거나 내용이 많은 카드는 `grid-column: span 2` 또는 `grid-row: span 2`로 더 넓게 배치한다.
- 카드 예시 주제: Overview, Quick Start, Architecture, Tech Stack, Key Features, Services/Components, API, Configuration, Data Storage, Monitoring 등 — 레포에 맞게 선택
- `grid-template-columns: repeat(N, 1fr)` 으로 열 수를 설정하고, 전체 너비는 1400px 내외로 넓게 잡아 카드들이 숨 쉬도록 한다

**카드 스타일 지침:**
- 라이트 테마 전용: 페이지 배경 `#f0f2f5`, 카드 배경 `#ffffff`, 카드 `border-radius: 10px`, `box-shadow: 0 2px 8px rgba(0,0,0,0.08)`
- 카드 상단에 컬러 `border-top: 4px solid {카테고리 색}` 으로 카테고리를 색으로 구분 (예: 개요계열 파랑, 기술스택 초록, API 주황 등)
- 카드 제목은 `<h2>` 또는 `<h3>`, 내용은 bullet list나 테이블, 코드 블록으로 구성
- 코드 블록은 밝은 배경(`#f4f4f4`)에 진한 텍스트
- 다크 배경 금지 (헤더 포함 어떤 영역도)

**전체 페이지 구조:**
```
[헤더: 레포 이름 + 한줄 설명 + 뱃지들]
[TL;DR 섹션 — 헤더 바로 아래]
[칸반 그리드 — 카드들이 2차원으로 배열]
[푸터]
```

**언어 규칙**: 서술 설명글은 한국어로 작성. 명령어·키워드·코드 블록·기술 용어·고유명사는 영어 원문 유지

### 3.5. HTML에 TL;DR 섹션 삽입

HTML 파일을 완성한 직후, 전체 내용을 다시 읽고 문서 맨 위에 TL;DR 섹션을 추가한다. 이 섹션은 긴 치트시트를 처음 보는 사람이 30초 안에 레포의 핵심을 파악할 수 있도록 돕는 것이 목적이다.

삽입 위치:
- 헤더 섹션(`<div class="header">` 등) **바로 아래**, 칸반 그리드 시작 전
- 칸반 그리드와 같은 너비로 맞추되, 별도의 단독 행으로 배치 (그리드 안에 넣지 않는다)

TL;DR 섹션 내용 구성:
- **한 줄 요약**: 이 레포가 무엇인지 한 문장으로
- **핵심 포인트 3~5개**: bullet point로, 각 항목은 짧고 구체적으로 (기능·특징·사용 대상 중심)
- **빠른 시작 명령어**: 설치/실행 명령이 있다면 `<code>` 태그로 1~2줄 표시

스타일 지침:
- 라이트 테마에 어울리는 연한 강조 배경(예: `#fff8e1`, `#e8f5e9`, `#e3f2fd`)
- `border-left: 4px solid` 로 시각적 구분
- 라이트 테마 규칙 유지 (다크 배경 금지)
- 언어 규칙 동일하게 적용 (설명글 한국어, 명령어·키워드 영어 유지)

HTML 파일을 직접 수정(파일 읽기 → TL;DR 블록 삽입 → 파일 저장)해서 완성한다.

### 4. Playwright로 스크린샷

`export/{title}-overview.html`을 Playwright로 열어 스크린샷을 찍는다.

- 파일 경로를 `file://` URL로 변환해서 브라우저로 열기
- 뷰포트 너비 1200px, 높이는 콘텐츠 전체가 들어오도록 fullPage 스크린샷
- 저장 위치: `export/{title}-overview.png`

Windows에서 `file://` URL 변환:
```
C:\Users\...\export\foo.html  →  file:///C:/Users/.../export/foo.html
```

### 5. Markdown 요약 생성

HTML의 각 `<h2>` 섹션을 기준으로 `export/{title}-overview.md`를 생성한다.

- 파일 상단에 레포 이름과 URL 헤더
- 각 섹션을 `## {섹션명}` 으로 구분
- 내용은 bullet point 또는 짧은 문단으로 요약 (원문 그대로 붙여넣지 말고 핵심만 추출)
- 코드 예시는 코드 블록으로 유지

---

## 완료 보고

세 파일이 모두 생성되면 다음 형식으로 보고한다:

```
✅ repo-scanner 완료: {owner}/{repo}

📄 export/{title}-overview.html
🖼  export/{title}-overview.png
📝 export/{title}-overview.md
```

파일 경로는 현재 작업 디렉토리 기준 상대 경로로 표시한다.

---

## 에러 처리

- deepwiki.com에 해당 레포 페이지가 없으면: GitHub README와 레포 메타정보(stars, description, topics, top languages)만으로 치트시트를 구성한다.
- Playwright 스크린샷 실패 시: 에러 메시지를 출력하고 HTML/MD 파일은 정상 저장한다.
- `export/` 디렉토리 생성 실패 시: 현재 디렉토리에 파일을 저장하고 사용자에게 알린다.
