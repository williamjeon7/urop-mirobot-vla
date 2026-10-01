# Custom Task 실행 파일

5장의 Panda 초기 장면과 6–9장의 검증에 사용한 코드와 BDDL이다. 실행 원본은 `../LIBERO/`에 있다. 각 Task에는 필요한 물체·Fixture만 남겼다.

## VSCode PowerShell에서 실행

새 터미널에서 아래 경로를 설정한다. 설치된 `libero` 환경이 없다면 [본문 3–4장](../NewTaskBDDL.md)의 설치 과정을 먼저 진행한다.

```powershell
$projectRoot = Join-Path $env:USERPROFILE 'Desktop\PML\urop\mirobot-vla'
$liberoRoot = Join-Path $projectRoot 'docs\W5\LIBERO'
$taskBundle = Join-Path $projectRoot 'docs\W5\custom_task_validation'
$liberoPython = Join-Path $env:USERPROFILE 'anaconda3\envs\libero\python.exe'
$liberoEnvironment = Split-Path -Parent $liberoPython
$env:PATH = "$liberoEnvironment;$liberoEnvironment\Library\bin;$liberoEnvironment\Scripts;$env:PATH"
if (-not (Test-Path -LiteralPath "$liberoRoot\setup.py")) {
    git clone https://github.com/Lifelong-Robot-Learning/LIBERO.git $liberoRoot
    if ($LASTEXITCODE -ne 0) { throw 'LIBERO clone failed' }
    git -C $liberoRoot checkout 8f1084e3132a39270c3a13ebe37270a43ece2a01
    if ($LASTEXITCODE -ne 0) { throw 'LIBERO checkout failed' }
}
if (-not (Test-Path -LiteralPath "$liberoRoot\check_libero_setup.py")) {
    New-Item -ItemType Directory -Path "$liberoRoot\custom_tasks" -Force | Out-Null
    Copy-Item "$taskBundle\*.py" "$liberoRoot\" -Force
    Copy-Item "$taskBundle\requirements-windows-validation.txt" "$liberoRoot\" -Force
    Copy-Item "$taskBundle\custom_tasks\*.bddl" "$liberoRoot\custom_tasks\" -Force
    Copy-Item "$taskBundle\libero\libero\*" "$liberoRoot\libero\libero\" -Recurse -Force
}
Set-Location -LiteralPath $liberoRoot
$env:MUJOCO_GL = 'wgl'
$env:NUMBA_DISABLE_JIT = '1'
& $liberoPython .\check_libero_setup.py
if ($LASTEXITCODE -ne 0) { throw 'Resolve the setup error before running a task' }
```

각 실행은 위 준비가 끝난 같은 터미널에서 진행한다.

```powershell
& $liberoPython .\test_panda_initial_pose.py
& $liberoPython .\test_libero_tabletop.py
& $liberoPython .\test_custom_bddl.py --headless --steps 60 --size 512 --seed 0 --record --predicate-test
& $liberoPython .\test_panda_drawer_info.py
& $liberoPython .\test_panda_drawer_action.py --headless --size 512 --seed 0
& $liberoPython .\test_milk_source_scene.py
& $liberoPython .\test_custom_task_variants.py --task both --seed 0 --size 512
& $liberoPython .\test_extended_custom_tasks.py --case all --seed 0 --size 512
& $liberoPython .\test_custom_predicate_conditions.py
& $liberoPython .\test_tabletop_configuration.py
```

`test_milk_source_scene.py`는 우유 모델을 사용하는 공식 Tabletop 장면의 초기 상태를 렌더링한다. `test_tabletop_configuration.py`는 작업대 크기 변경과 초기화까지만 검사한다. C–F 실행 파일은 Object·Fixture·Predicate·Problem 모듈을 import해 등록한다.

## 사진과 영상 반영

현재 PC에서 확인한 FFmpeg를 지정해 결과를 반영한다.

```powershell
$liberoFFmpeg = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe'
if (-not (Test-Path -LiteralPath $liberoFFmpeg)) { throw 'Set liberoFFmpeg to the installed ffmpeg.exe path' }
& $liberoPython .\export_custom_task_media.py --chapter both --ffmpeg $liberoFFmpeg
```

내보내기는 초기 상태와 실제 Panda 동작의 Goal·파지·해제·유지 검사를 통과한 결과에 적용한다. `--chapter 8`이나 `--chapter 9`로 해당 장의 결과만 선택할 수 있다. `reference_code`는 공식 코드와 MIT 라이선스의 참고 사본이며, 복원할 확장 코드와 별도로 보관한다.
