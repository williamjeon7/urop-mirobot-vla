# Custom Task 실행 파일

5.2의 Panda 초기 자세와 6~9장의 검증을 재현하는 코드와 BDDL이다. 실행 원본은 `../LIBERO/`에 있다. [8장 결과](../images/custom_task_validation/)와 [9장 결과](../images/extended_task_validation/)의 GIF는 실제 MP4 프레임으로 만든 미리보기다.

`libero` conda 환경은 [본문의 설치 절차](../NewTaskBDDL.md)에 따라 준비한다. 새로 받은 상위 저장소에 LIBERO 코드가 없으면 아래 조건부 명령으로 받는다. 이미 설치된 LIBERO가 있으면 같은 경로에 검증 파일을 복원한다. 9장 실행 코드는 새 물체·Fixture·Predicate·환경 모듈을 가져와 등록한다.

검증에 사용한 공식 LIBERO 기준 버전은 `8f1084e3132a39270c3a13ebe37270a43ece2a01`이다. `reference_code`는 문서에서 인용한 공식 소스와 원본 MIT 라이선스를 보관하는 참고용이며, 아래 복원 명령의 복사 대상에서 제외된다.

```powershell
if (-not (Test-Path -LiteralPath .\docs\W5\LIBERO\setup.py)) {
    git clone https://github.com/Lifelong-Robot-Learning/LIBERO.git .\docs\W5\LIBERO
    git -C .\docs\W5\LIBERO checkout 8f1084e3132a39270c3a13ebe37270a43ece2a01
}
$taskBundle = Resolve-Path .\docs\W5\custom_task_validation
$liberoRoot = Resolve-Path .\docs\W5\LIBERO
New-Item -ItemType Directory -Path "$liberoRoot\custom_tasks" -Force
Copy-Item "$taskBundle\*.py" "$liberoRoot\" -Force
Copy-Item "$taskBundle\custom_tasks\*.bddl" "$liberoRoot\custom_tasks\" -Force
Copy-Item "$taskBundle\libero\libero\*" "$liberoRoot\libero\libero\" -Recurse -Force
conda activate libero
cd $liberoRoot
python test_panda_initial_pose.py
python test_custom_task_variants.py --task both --size 512
python test_extended_custom_tasks.py --case all --size 512
python test_custom_predicate_conditions.py
python export_custom_task_media.py --chapter both --ffmpeg 'FFmpeg 실행 파일 경로'
```

FFmpeg가 PATH에 있거나 `imageio-ffmpeg`가 설치돼 있으면 `--ffmpeg`를 생략한다. `--chapter 8` 또는 `--chapter 9`로 해당 장의 결과만 내보낼 수 있다. 내보내기는 초기 상태와 실제 Panda 동작 후의 Goal·파지·해제·유지 조건이 모두 통과한 결과에만 실행된다.
