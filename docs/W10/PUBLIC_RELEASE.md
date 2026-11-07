# GitHub 공개 전환 — 계획

> **설계** · 확인 2026-11-07 · 기준 `main@8533472c`, GitHub 공식 문서 (11/07 확인)
> 비공개 저장소를 공개하기 전에 — 공개되면 무엇이 보이는지, 그중 빼거나 가릴 것을 어떤 순서로 찾아 처리할지. 정할 것은 8절.

배경: 우리 작업을 밖에서도 볼 수 있게 저장소를 공개하려 한다 (11/07 사용자). 설정에서 공개로 바꾸기만 하면 지금 파일뿐 아니라
커밋 215개의 옛 버전과 작성자 메일까지 같이 공개되므로, 바꾸기 전에 찾을 것과 순서를 먼저 정한다.

## 0. 요약

- 공개되면 지금 파일만 보이는 게 아니다. 히스토리 전체(지금은 없는 경로 2,269개 포함), 작성자 이름·메일 5종(개인 메일 2·학교 메일 1), LFS 파일 2만여 개(9.45 GB), GitHub 에 있다면 Actions 기록까지 보인다 (1절)
- 찾을 것은 일곱 갈래 — 접속·보안 정보, 사람 정보, 학교·연구 내부 자료, 저작권, 용량, 저장소 정리, GitHub 설정 (3절)
- **제안 (확인 전)**: 지금 저장소는 비공개로 계속 쓰고, 검사·정리한 사본으로 **새 공개 저장소**를 만든다 (4절 B1). 이 저장소를 고쳐서 공개하면(A) 옛 커밋과 LFS 파일이 GitHub 에 남을 수 있고, 남이 LFS 를 받을 때마다 우리 계정 전송량이 줄어든다
- 지금까지는 파일 이름·크기·커밋 정보만 봤다. **파일 내용 검사는 이 계획을 확인한 뒤** 시작한다 (5절 묶음 2)
- 먼저 정할 것 — 공개 방식(D1), 교수님·동료 동의(D2)

## 1. 공개로 바꾸면 보이는 것

| 무엇 | 지금 (11/07) | 공개되면 |
| --- | --- | --- |
| 지금 파일 (`main`) | 23,936개 | 누구나 보고 받는다 |
| 히스토리 | 커밋 215개 (9/8 부터). 지금 `main` 에 없는 경로 2,269개 (지웠거나 옮긴 것) | 커밋을 열면 지운 파일과 옛 내용이 그대로 보인다 |
| 커밋 정보 | 작성자 5종 — 개인 메일 2, 학교 메일 1, GitHub noreply 2. 커밋 126개의 메시지에 Claude 세션 링크 | 모든 커밋의 이름·메일·메시지 |
| Git LFS | `main` 21,885개 · 9.45 GB (히스토리 전체 22,289개) | 누구나 받는다. 받는 양은 **소유자 계정의 전송량**으로 잡힌다 |
| GitHub 쪽 | 이슈·PR·위키·릴리스·Actions 기록 — 있는지 아직 모름 (서버에 `gh` 없음) | Actions 기록과 로그도 공개된다 |

GitHub 문서에서 확인한 것 (11/07):

- 공개로 바꾸면 Actions 기록과 로그가 모두에게 보이고, 별·watcher 는 지워지고, push ruleset 은 꺼진다. 비공개 fork 는 떨어져 나가 따로 된 비공개 저장소가 된다 — [Setting repository visibility](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility)
- 히스토리를 고쳐 강제 푸시해도 옛 커밋은 **clone·fork, SHA 로 여는 캐시 화면, 그 커밋을 가리키는 PR** 에 남는다. 캐시와 PR 참조는 GitHub Support 에 요청해야 지워지는데, 토큰처럼 교체하면 해결되는 것과 민감하지 않은 정보는 지워 주지 않는다 — [Removing sensitive data from a repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)
- 토큰·비밀번호가 나오면 **먼저 폐기·교체**한다 (같은 문서)
- LFS 파일은 히스토리를 고쳐도 GitHub 저장 공간에 남는다. 지우려면 저장소를 지우고 다시 만들거나 Support 에 요청한다 — [Removing files from Git LFS](https://docs.github.com/en/repositories/working-with-files/managing-large-files/removing-files-from-git-large-file-storage)
- LFS 는 남이 받아도 소유자 전송량으로 잡힌다. GitHub Free 는 한 달에 전송 10 GiB·저장 10 GiB 이고, 결제 수단 없이 전송량을 넘기면 다음 달까지 **계정의 LFS 가 꺼진다** — [Git LFS billing](https://docs.github.com/en/billing/concepts/product-billing/git-lfs). `main` 의 LFS 9.45 GB 를 누가 한 번 통째로 받으면 거의 다 쓰고, 그러면 노트북 녹화를 올리고 받는 우리 작업도 막힌다 (요금제는 확인 필요)

## 2. 어디에 무엇이 있나 (사전 조사)

파일 이름·크기·커밋 정보만 본 결과다. 내용은 아직 안 열었다.

| 항목 | 값 |
| --- | --- |
| 폴더별 | `Mirobot_data/` 18,000 · `docs/` 5,571 (그중 `docs/W9` 5,313) · `data/` 210 · `trajectories/` 43 · `tools/` 41 · `tests/` 24 · `robot/` 12 · 루트 11 · `common/` 10 · `server/` 9 · `requirements/` 4 · `.vscode/` 1 |
| 종류별 | PNG 20,055 · JSON 768 · JSONL 538 · Python 167 · G-code 164 · MP4 100 · NPZ 100 · Markdown 73 · JPG 47 · log 21 · GIF 20 · HDF5 10 · pptx 5 · zip 3 · pkl 3 |
| 히스토리에만 있는 경로 | `docs/W9/data/` 2,209 · `Mirobot_data/W10/L13_red` 29 (다시 찍기 전) · `mirobot_control/` 11 · `docs/W4/Mirobot_Cosmos_LIBERO_사진포함` 사진과 zip 10 · 옛 문서·pptx 몇 개 |
| 큰 파일 (LFS 아님) | HDF5 10개 50–89 MB (`docs/W9/data/hdf5/mirobot_real/`, `.gitignore` 대상인데 강제로 추가됨), pptx 최대 72 MB. `.git/objects` 955 MB |
| 안을 따로 열어야 하는 파일 | pptx 5 · zip 3 (히스토리에 1개 더) · pkl 3 |
| 깨진 항목 | 루트 `mirobot-vla` — 이 저장소의 9/8 커밋(`aec05042`)을 가리키는 gitlink. GitHub 에서는 열리지 않는 하위 모듈로 보인다 |
| 서버에 있는 도구 | `git`, `ffprobe`, Python(`urop` env). gitleaks·trufflehog·detect-secrets·git-filter-repo·bfg·`gh` 는 없다 |

## 3. 찾을 것

| 분류 | 무엇 | 먼저 볼 곳 | 기본 처리 (제안) |
| --- | --- | --- | --- |
| ① 접속·보안 | 서버 IP·SSH 포트·계정 이름, 호스트 키, 개인 키, 토큰(HF·W&B·GitHub)·비밀번호 | `docs/SETUP_LINUX.md`, `docs/W10/DEPLOY_MIROBOT.md`, `start_mirobot_windows.*`, `server/`, `robot/`, `tools/`, zip 안, `.vscode/settings.json`, log | 토큰·키는 폐기·교체하고 뺀다. 주소·포트·계정은 `<SERVER_HOST>` 같은 자리표시로 바꾸고, 코드는 로컬 설정 파일(gitignore)에서 읽게 한다 |
| ② 사람 | 이름·메일·학번·전화, 얼굴·손이 나온 사진·영상, 사진 EXIF(GPS), pptx 작성자 정보, 경로 속 계정 이름(`/mnt/hdd/home/…`, `C:\Users\…`), 기기 일련번호 | 커밋 작성자, `docs/meetings/` (파일 이름에 이름이 든 것도 있다), pptx, 녹화 사진, JSON 메타데이터 | 이름은 역할(교수님·동료)로 바꾸고 메일은 지운다. 사람이 나온 사진은 빼거나 가린다 |
| ③ 학교·연구 내부 | 미팅 기록, 교수님 회신, 아직 발표하지 않은 결과, 내부 계획 | `docs/meetings/`, `docs/plan/`, `docs/W4/ANSWER.md`, `docs/ppt/` | 동의(D2) 전에는 공개판에서 뺀다 |
| ④ 저작권 | 외부 코드를 복사·수정한 것, 논문·제조사 그림. 우리 라이선스는 아직 없다 | `mirobot_control/` (히스토리), `docs/W6/rgb_blocks/`, pptx 그림, [../VENDORED.md](../VENDORED.md)·[../PAPERS.md](../PAPERS.md) 가 가리키는 것 | 출처와 원 라이선스를 적는다. 우리 라이선스는 D5 |
| ⑤ 용량 | LFS 9.45 GB, 50 MB 넘는 HDF5·pptx | `Mirobot_data/`, `docs/W9/data/` | 원본 데이터는 빼고 문서 그림만 (D4). 넣으면 같은 계정에 LFS 가 한 번 더 올라가고 전송량도 나간다 (1절) |
| ⑥ 정리 | 깨진 gitlink, 루트의 zip·pptx, `.aborted` 파일, pkl (남이 열면 코드가 실행될 수 있다) | 루트, `data/` | 빼거나 옮긴다 |
| ⑦ GitHub 설정 | 이슈·PR·위키·릴리스 내용, Actions 로그, 협업자, deploy key, webhook | GitHub 웹 설정 | A 방식일 때만. 사용자가 웹에서 본다 |

## 4. 공개 방식 (D1)

| | A. 이 저장소를 고쳐서 공개 | B. 새 공개 저장소 |
| --- | --- | --- |
| 하는 일 | 히스토리 전체를 `git filter-repo` 로 다시 쓰고 강제 푸시한 뒤 공개로 바꾼다 | 지금 저장소는 비공개로 둔다. 검사·정리한 파일만 새 저장소에 올린다 |
| 히스토리 | 고친 형태로 남는다 | B1: 첫 커밋 하나. B2: 공개할 경로만 남긴 히스토리를 옮긴다 |
| 검사할 범위 | 커밋 215개의 모든 파일 버전, 메시지, LFS 22,289개, GitHub 이슈·PR·Actions | B1: 올릴 파일만. B2: 올릴 경로의 모든 옛 버전 |
| 남는 위험 | 옛 커밋이 SHA 캐시·PR 참조에 남는다 (1절). 고치기 전 clone(서버·노트북·동료)에서 push 하면 다시 들어온다. LFS 는 저장소를 다시 만들어야 지워지고, 남이 받으면 우리 전송량이 나간다. 문서에 적어 둔 옛 커밋 해시가 옛 내용으로 가는 길이 된다 | 공개판을 갱신할 때 검사를 건너뛰는 것 |
| 같이 일하는 사람 | 모두 다시 clone 한다. 커밋 해시가 바뀌어 문서의 `기준` 해시가 안 맞는다 | 바뀌는 것 없음 |
| 설치 | git-filter-repo 2.47 이상 (승인 필요) | B1 없음. B2 는 git-filter-repo |
| 이후 작업 | 공개 저장소에 바로 커밋하니 매번 민감정보를 조심해야 한다 | 비공개에서 지금처럼 일하고, 정한 때에 공개판을 다시 내보낸다 (D7) |

**제안: B1** (확인 전)

1. 커밋 215개 모두에 작성자 메일이 붙어 있어, A 는 모든 커밋을 다시 써야 한다
2. 메일·IP 처럼 교체로 해결되지 않는데 비밀번호도 아닌 정보는 Support 가 캐시에서 지워 준다는 보장이 없다
3. LFS 파일 중 하나라도 빼야 하면 A 로는 GitHub 에서 지울 수 없다
4. 지금 저장소의 접속 절차·미팅 기록을 그대로 쓰면서 공개판만 따로 관리할 수 있다

대가: 공개판에는 커밋 이력이 없고, 갱신을 따로 해야 한다.

같은 이름(`mirobot-vla`)을 공개판에 쓰려면 지금 저장소 이름을 먼저 바꾼다. 이때 **서버·노트북·동료 clone 의 `origin` 주소를 먼저 고친다** —
안 고치면 옛 주소가 공개판을 가리켜, 옛 clone 에서 새 브랜치를 push 하는 순간 비공개 히스토리가 통째로 공개판에 들어간다.

## 5. 진행 순서

묶음마다 WORKLOG 항목을 남기고, 멈추는 곳은 사용자 판단이 필요한 곳뿐이다. 커밋은 사용자가 확인한 묶음만 한다.

| 묶음 | 하는 일 | 바뀌는 것 | 멈추는 곳 |
| --- | --- | --- | --- |
| 1. 계획 (11/07) | 공개 범위·현재 상태 조사, 찾을 것, 방식 비교 | 이 문서, WORKLOG, [../README.md](../README.md) 목록 | 계획 확인, D1·D2 |
| 2. 지금 파일 검사 | `main` 의 텍스트 패턴 검사, 메타데이터(EXIF·pptx·zip·HDF5 속성·MP4), 사진 표본 보기 | 없음 (읽기만) | 분류마다 지움·가림·둠, D3–D5 |
| 3. 히스토리 검사 | A·B2 만. 모든 커밋의 파일 버전, 커밋 메시지 | 없음 | 히스토리에서 고칠 범위 |
| 4. 정리 | B1: 저장소 밖 새 폴더에 고른 파일만 복사하고 가린 뒤 새로 `git init` — 지금 `.git` 을 복사하거나 fork 로 만들면 옛 객체가 같이 간다. 커밋 작성자는 noreply 메일. README 머리말·LICENSE·출처. A: 작업 트리 수정 커밋, 복제본에서 히스토리 다시 쓰기 | B1: 저장소 밖 폴더. 접속 정보를 코드에서 빼는 수정은 이 저장소에도 | 바뀐 내용 확인 |
| 5. 확인 | 정리본 다시 검사, 새로 clone 해서 보기, 문서 링크 깨짐 | 없음 | 공개해도 되는지 최종 확인 |
| 6. 공개 | **사용자** — B: 새 저장소를 만들어 push. A: 강제 푸시 후 공개 전환 | GitHub | — |
| 7. 공개 후 | 로그아웃한 창에서 보기, Security 탭 알림, LFS 사용량 | 필요하면 공개판 수정 | — |

- 묶음 2 는 D1 을 정하는 동안 해도 된다. 어느 방식이든 지금 파일은 깨끗해야 한다
- 토큰·개인 키가 나오면 순서와 상관없이 바로 알린다. 폐기·교체는 사용자가 해당 사이트에서 한다

## 6. 검사 방법

설치 없이 `git`, `ffprobe`, Python(`urop` env)으로 한다.

- **텍스트** — `git cat-file --batch` 로 커밋된 내용을 꺼내고, 같은 내용은 한 번만 검사한다. 히스토리 검사도 같은 방식. 한글 경로는 `-c core.quotePath=false`
  - 패턴: IP 주소, `ssh -p`·`user@host`, `BEGIN … PRIVATE KEY`, 토큰 형식(`hf_`, `ghp_`, `github_pat_`, `sk-`, AWS `AKIA`), `WANDB_API_KEY`, `password`·`token`·`secret` 에 값을 넣은 줄, 메일, 전화번호, 절대 경로(`/mnt/hdd/home/`, `/home/`, `C:\Users\`)
  - 사람 이름: 찾을 이름 목록을 사용자에게 받는다 (목록도 저장소 밖에 둔다)
- **pptx·zip** — 풀지 않고 안의 목록과 글을 읽는다. pptx 는 작성자(`docProps/core.xml`)·슬라이드 글·노트·그림 수
- **사진·영상** — 전체 EXIF(GPS·기기·작성자)와 MP4 메타데이터(`ffprobe`). 녹화 폴더마다 처음·중간·끝 장면을 한 장으로 모아, 사람·모니터 화면·이름표가 보이는지 같이 본다
- **HDF5·NPZ·pkl** — 속성과 키 이름만 읽는다. pkl 은 `pickle.load` 하지 않고 `pickletools` 로 본다
- **보조 도구** — 정규식 검사를 한 번 더 확인하고 싶으면 gitleaks, A·B2 를 고르면 git-filter-repo. **둘 다 설치 전에 승인** (D6)

## 7. 기록 규칙 — 이 문서도 공개된다

- 찾은 실제 값(IP·메일·이름·토큰)과 파일별 목록은 **저장소 밖** `~/UROP_public_audit/` 에만 둔다 (제안). 저장소 안에 두면 공개판에 같이 들어갈 수 있다
- 이 문서와 WORKLOG 에는 분류·개수·파일 위치만 적고, 값은 `<SERVER_IP>` 처럼 가린다
- 처리 결정은 분류마다 표로 남긴다 (누가·언제)

## 8. 정할 것

| # | 정할 것 | 선택지 | 제안 (확인 전) | 언제까지 |
| --- | --- | --- | --- | --- |
| D1 | 공개 방식 | A 이 저장소 고쳐서 / B1 새 저장소 첫 커밋 / B2 새 저장소에 히스토리 골라 옮김 | B1 | 묶음 3 전 |
| D2 | 공개 동의 | 교수님(연구 내용·미팅 기록), 동료(작성자 정보·맡은 코드) | 공개 전에 받는다 | 묶음 6 전 |
| D3 | 미팅 기록·교수님 회신·계획 문서 | 공개 / 가려서 공개 / 뺌 | 동의 전에는 뺀다 | 묶음 4 전 |
| D4 | 원본 데이터 (`Mirobot_data/`, `docs/W9/data/`) | 전부 / 표본만 / 뺌 (나중에 따로 공개) | 빼고 문서 그림만 | 묶음 4 전 |
| D5 | 라이선스 | MIT / Apache-2.0 / 없음 (보기만 가능) | 사용자가 정한다 (외부 코드 조건을 본 뒤) | 묶음 4 전 |
| D6 | 도구 설치 | gitleaks, git-filter-repo | 설치 없이 먼저 하고, 필요하면 그때 요청 | 묶음 2 중 |
| D7 | 공개판 갱신 (B) | 한 번만 / 주마다 / 프로젝트 끝(W14) | 나중에 정한다 | 공개 후 |

## 9. 사용자만 하는 것

- 공개 전환, 새 저장소 만들기, push·강제 푸시. 한 번 공개되면 누가 받아 갔는지 알 수 없어 되돌릴 수 없다
- 토큰·키 폐기와 교체
- 교수님·동료 동의
- GitHub 웹 설정 확인 (A 일 때 ⑦)
- (선택) GitHub 계정 메일 설정에서 "Keep my email addresses private" 와 "Block command line pushes that expose my email" 켜기 — 앞으로의 커밋에 개인 메일이 안 붙게
