# 논문

> **절차** · 확인 2026-09-23
> 프로젝트가 기대는 논문 목록과 받는 법. PDF 는 `.gitignore` 로 빠져 있어 clone 에 따라오지 않는다.

**PDF 는 각 기기에서 받고, 논문에서 확인한 내용은 docs 에 적어 공유한다.**
히스토리에 바이너리가 쌓이지 않게 하려는 것이다 — 한 번 커밋한 PDF 는 지워도 히스토리에 남는다.
외부 저장소를 다루는 [VENDORED.md](VENDORED.md) 와 같은 방식이다.

## 받는 법

위치는 **repo 최상위 `papers/`** 다 (서버면 `~/UROP/papers`, 노트북이면 `C:\mirobot-vla\papers`).

```bash
# Git Bash · Linux
mkdir -p papers
curl -L -o papers/libero.pdf    https://arxiv.org/pdf/2306.03310
curl -L -o papers/robosuite.pdf https://arxiv.org/pdf/2009.12293
curl -L -o papers/cosmos.pdf    https://arxiv.org/pdf/2601.16163
```

```powershell
# PowerShell — curl 이 아니라 curl.exe. 5.1 에서 curl 은 Invoke-WebRequest 의 별칭이라 -L -o 가 안 먹는다
New-Item -ItemType Directory -Force papers | Out-Null
curl.exe -L -o papers/libero.pdf    https://arxiv.org/pdf/2306.03310
curl.exe -L -o papers/robosuite.pdf https://arxiv.org/pdf/2009.12293
curl.exe -L -o papers/cosmos.pdf    https://arxiv.org/pdf/2601.16163
```

## 목록

| 파일 | 논문 | 무엇을 볼 때 |
|---|---|---|
| `libero.pdf` | Liu et al., *LIBERO: Benchmarking Knowledge Transfer for Lifelong Robot Learning*, NeurIPS 2023 Datasets & Benchmarks · [arXiv:2306.03310](https://arxiv.org/abs/2306.03310) | task suite 구조, **task = 초기 상태 분포 + 목표** 라는 정의(2.2절), 물체 배치를 정하는 BDDL(4.1절, 부록 C). **로봇 초기 자세는 다루지 않는다** — 분포는 물체의 종류·배치·상태만 (9/23 확인) |
| `robosuite.pdf` | Zhu et al., *robosuite: A Modular Simulation Framework and Benchmark for Robot Learning* · [arXiv:2009.12293](https://arxiv.org/abs/2009.12293) | Panda 컨트롤러(OSC_POSE, 스프링-댐퍼), 로봇 모델과 초기화 — [W3/CONTROL.md](W3/CONTROL.md) 의 근거 쪽 |
| `cosmos.pdf` | Kim et al., *Cosmos Policy: Fine-Tuning Video Models for Visuomotor Control and Planning*, 2026 · [arXiv:2601.16163](https://arxiv.org/abs/2601.16163) | 우리가 쓰는 정책. proprio·액션 형식. `cosmos-policy/README.md` 가 인용하는 원문 |

**받지 않는 것 (유료)** — Khatib, *A unified approach for motion and force control of robot manipulators:
The operational space formulation*, IEEE Journal of Robotics and Automation, 1987. 스프링-댐퍼 제어(OSC)의 원전. 서지만 둔다.

## 논문을 인용할 때

- **확인한 사실은 그 사실의 주인 문서에** 적는다. 여기는 목록만 둔다 ([README.md](README.md) "한 사실의 주인은 한 문서다")
- 출처는 **논문 이름 + 절·쪽** 으로 — `LIBERO 논문 4.2절` 처럼. PDF 가 없는 기기에서도 찾아갈 수 있게
- **구현 세부는 논문에 없을 수 있다.** 기본값·상수 같은 숫자는 보통 소스 코드에 있다. 논문은 설계 의도, 숫자는 소스로 확인한다
