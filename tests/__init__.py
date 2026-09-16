"""테스트. 런타임 의존성이 아니다.

`__init__.py` 가 필요한 이유 — 서버 `.venv` 의 site-packages 에 다른 `tests` 패키지가 있어서,
이 폴더가 namespace package 로 남으면 그쪽이 이긴다. 정식 패키지로 만들어 먼저 잡히게 한다.
"""
