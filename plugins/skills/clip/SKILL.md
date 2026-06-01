---
name: clip
description: 텍스트를 rstrip(각 줄 오른쪽 공백 제거)해서 tmp/clipboard.txt에 저장한다. Claude Code 화면에서 복사한 텍스트를 다른 곳에 붙여넣을 때 오른쪽 공백이 채워지는 문제를 해결할 때 사용한다. /clip <텍스트> 형태로 호출한다.
---

사용자가 입력한 텍스트의 각 줄 오른쪽 공백을 제거(rstrip)한 뒤 `tmp/clipboard.txt`에 덮어쓴다.
기존 내용은 무시하고 현재 입력만 남긴다.

다음 명령을 실행하고 결과를 그대로 전달한다:

```sh
python "$SKILL_DIR/scripts/clip.py" "$ARGUMENTS"
```
