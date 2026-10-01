from dataclasses import dataclass


@dataclass
class CrossSessionNameData:
    name: str  # ListAgents 이름 (등록부 `name`, 없으면 cwd 폴더 이름). 못 찾으면 ''
    ref: str   # ListAgents `[ref]` 6자리. 소켓 경로가 없으면 ''
