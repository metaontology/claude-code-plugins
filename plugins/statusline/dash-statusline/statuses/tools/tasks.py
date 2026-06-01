from domain.monitor.status.tools.tasks import TasksItemData
from domain.monitor.status.tools.events import ToolsEventUse, ToolsEventResult


class TasksParser:
    """TodoWrite 도구 호출을 파싱해 todo 진행 상황을 추적한다.

    Claude Code에서 TodoWrite는 사용자가 직접 호출하는 명령어가 아니라,
    Claude가 멀티스텝 작업 수행 시 스스로 판단해 호출하는 내부 도구다.
    (Explore subagent를 Claude가 필요할 때 자율 호출하는 것과 같은 맥락)

    이전에 존재하던 /todos 슬래시 명령어는 deprecated되었으며,
    현재는 Claude가 TodoWrite({ todos: [...] }) 형태로 호출할 때
    transcript에 기록되고, 이 파서가 그 이벤트를 읽어 상태를 갱신한다.

    전형적인 흐름:
      1. Plan mode: Claude가 .md 파일에 계획 작성 (이 파서와 무관)
      2. Edit mode 실행 요청: Claude가 TodoWrite로 todo 목록 초기화
      3. 각 단계 완료 시: Claude가 TodoWrite로 status 갱신
         → on_use()가 호출될 때마다 최신 todos로 덮어쓴다

    주의: TodoWrite는 Claude가 필요하다고 판단할 때만 호출된다.
    단순한 작업이라면 TodoWrite 없이 바로 실행하므로, 실행 중에도
    statusline에 todo 진행 상황이 표시되지 않을 수 있다.
    """

    def __init__(self):
        self._todos = []

    def on_use(self, ev: ToolsEventUse):
        self._todos = ev.inp.get('todos', [])

    def on_result(self, ev: ToolsEventResult):
        pass

    def result(self) -> TasksItemData:
        return TasksItemData(todos=list(self._todos))

    def render(self, data: TasksItemData, palette, style) -> str:
        if not data.todos:
            return '📋'
        done = sum(1 for t in data.todos if t.get('status') == 'completed')
        total = len(data.todos)
        if done == total:
            return f'📋 {palette.ok}✓ {done}/{total}{palette.reset}'
        return f'📋 {done}/{total}'
