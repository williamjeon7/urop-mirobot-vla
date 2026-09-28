# LIBERO 기반 Mirobot 실물 환경 구성과 Cosmos Policy 학습

## 1. 연구 목표와 진행 흐름

LIBERO로 구성한 custom 환경의 **작업대, 로봇과 카메라의 상대 배치, 기준 시작 자세**를 참고해 Mirobot 실험 환경을 만든다. 여기서 custom 환경은 연구에 맞게 설정을 바꾼 시뮬레이션 장면이고, task는 로봇이 수행할 구체적인 작업이다. 이 기본 환경을 유지하면서 실물 task와 물체 배치를 정하고, 사람이 Mirobot을 조작해 시연 데이터를 수집한다. 수집한 영상·로봇 상태·동작으로 Cosmos Policy를 추가 학습한 뒤, 실제 환경에서 정책을 실행해 성공률을 평가한다.

환경 구성 단계의 과제는 **① 공개 레퍼런스 코드로 시뮬레이션 환경을 비교하고, ② Mirobot 실물 배치의 기준으로 사용할 환경을 선정한 뒤, ③ 두 로봇의 사용 가능한 작업 영역 사이에 비례식을 세워 설치 위치를 정하는 것**이다. 이에 따라 환경 비교·선정은 2절에서, 실측값을 이용한 배치 계산과 설치 방법은 3절에서 다룬다.

전체 흐름은 **LIBERO custom 기본 환경 설정 → 실물 기본 환경 구성 → 실물 task·물체 배치 결정 → Mirobot 시연 수집 → Cosmos Policy 추가 학습 → 실물 추론·평가**다. 시뮬레이터는 기본 환경과 관측 구조의 기준으로 사용하고, 본 실험의 학습 데이터는 실제 Mirobot에서 수집한다.

## 2. 실험 환경 비교와 LIBERO 선택

이번 연구에서는 시뮬레이션의 작업대·카메라·시작 자세를 참고해 실물 기본 환경을 구성한다. 따라서 환경을 고를 때는 다음 세 조건을 우선한다.

1. **실물 배치와의 대응:** 탁상에 고정한 단일 로봇 팔과 고정·손목 카메라 구성을 기준으로 삼을 수 있는가.
2. **초기 조건의 재현:** 작업대·로봇·카메라 설정과 시작 상태를 코드에서 확인하고, 수정한 조건으로 다시 초기화할 수 있는가.
3. **정책 관측과의 연결:** 환경에서 얻은 영상과 로봇 상태가 정책 입력으로 전달되는 과정을 공개 코드로 확인할 수 있는가.

### 시뮬레이션 환경 비교

아래는 기본 환경을 구축할 출발점을 비교한 것이다. 장단점은 각 항목에 연결한 공개 코드와 예제를 위 조건에 비추어 판단했다. 비교 범위는 해당 구현이 제공하는 장면·초기화·관측 연결이다.

| 환경 | 장점 | 단점·추가 작업 | 이번 연구에서의 판단 |
| --- | --- | --- | --- |
| **[LIBERO](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/problems/libero_tabletop_manipulation.py) — Cosmos Policy-LIBERO 실행 환경** | [tabletop 장면](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/problems/libero_tabletop_manipulation.py)과 [환경 래퍼](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/env_wrapper.py)에서 작업대·카메라·초기 상태 설정을 확인할 수 있다. OpenVLA-OFT와 Cosmos Policy의 실행 코드로 관측 연결도 확인된다. | 기본 로봇은 Panda이므로 Mirobot의 도달 범위·시작 자세·그리퍼와 실물 제어는 별도로 맞춰야 한다. | 필요한 기본 환경과 관측 흐름이 갖춰져 있어, 실물에 맞춘 배치·보정에 집중할 수 있다. |
| [RoboCasa](https://github.com/robocasa/robocasa) | [환경 생성 함수 `create_env()`](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/utils/env_utils.py)에서 로봇·카메라·주방 배치를 설정한다. 다양한 설비·물체를 포함한 장면을 구성하기 좋다. | 소형 탁상 구성에 맞는 장면과 관측 조건을 별도로 정해야 한다. | 설비와 장면의 다양성은 장점이지만, 고정된 기본 작업대를 옮기는 현재 범위에서는 활용도가 낮다. |
| [Isaac Sim — URDF 가져오기 예제](https://docs.isaacsim.omniverse.nvidia.com/latest/importer_exporter/import_urdf.html) | 공식 Python 예제에서 URDF 로봇 모델을 변환해 장면으로 여는 과정을 확인할 수 있다. Mirobot 모델을 불러오는 출발점으로 사용할 수 있다. | 검토한 예제에는 작업대·카메라·초기화·정책 관측 연결이 포함되지 않아 해당 구성을 추가해야 한다. | 로봇 모델을 직접 구성할 때 참고한다. 이번 기본 환경 기준으로 사용하려면 작업 장면과 관측 코드까지 확보해야 한다. |
| [Gazebo 기반 Mirobot 공개 예제](https://github.com/wlkata/RosForMirobot-master/blob/8a60a4ce16186ddbb9393e20bb904cbab61fc884/mirobot_gazebo/launch/mirobot_bringup_moveit.launch) | launch가 Mirobot 모델·관절 상태·6축 궤적 제어기·MoveIt/RViz를 연결한다. 모델과 관절 제어 구조를 직접 참고할 수 있다. | ROS 1·Gazebo Classic 기반이며 실행 버전 조합이 고정돼 있지 않다. 해당 launch 경로에 카메라·정책 관측 연결이 없고 실물 전송 노드도 비활성화돼 있어, 센서·동기화·정책 변환·실물 통신을 추가해야 한다. | Mirobot 기구·관절 제어의 참고 코드로 활용한다. 영상 기반 학습에는 별도의 환경·관측 구성이 필요하다. |

**환경별 대표 화면.** LIBERO·RoboCasa·Isaac Sim은 공식 논문·문서의 예시 이미지이며, 이번에 분석한 코드를 새로 실행한 결과와 구분한다. Mirobot Gazebo는 아래에 밝힌 조건으로 직접 렌더링했다.

| LIBERO |    RoboCasa |
| --- | --- |
| ![LIBERO 논문의 탁상 조작 초기 장면](images/environment_libero_spatial.png) | ![RoboCasa 공식 문서의 주방 시뮬레이션 장면](images/environment_robocasa.jpg) |
| 같은 물체의 공간 배치를 달리한 탁상 장면. [LIBERO 논문 Figure 8](https://arxiv.org/abs/2306.03310) | 설비·배치·로봇 구성이 다른 주방 장면 모음. [RoboCasa 공식 v0.2 문서](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/docs/_versions/v0.2/images/robocasa-banner_v0.2.jpg) |

| Isaac Sim URDF 가져오기 예제 | Mirobot Gazebo |
| --- | --- |
| ![Isaac Sim 공식 튜토리얼에서 불러온 UR10 모델](images/environment_isaac_ur10.png) | ![공식 Mirobot 모델을 Gazebo에서 렌더링한 화면](images/environment_mirobot_gazebo.png) |
| 공식 **UR10** 모델 가져오기 화면. Mirobot 장면은 별도 구성해야 한다. [NVIDIA 공식 문서](https://docs.isaacsim.omniverse.nvidia.com/latest/importer_exporter/import_urdf.html) | [공식 Mirobot 모델](https://github.com/wlkata/RosForMirobot-master/blob/8a60a4ce16186ddbb9393e20bb904cbab61fc884/mirobot_urdf_2/urdf/mirobot_urdf_2.xacro)을 Gazebo 11.15.1에서 직접 렌더링했다. ROS 제어 플러그인을 제외하고 표시용 지면·조명·촬영 시점을 추가한 정적 장면이다. |

### 환경 구성 코드의 주요 함수

환경의 장단점을 판단한 근거를 주요 함수와 설정 파일별로 정리했다. 아래 내용은 공개 소스 분석이며, 각 후보의 Mirobot 성능 비교 결과는 아니다. 위 Gazebo 실행에서는 모델 표시를 확인했으며 ROS·MoveIt 제어와 정책 연동은 검증하지 않았다. 코드의 기본 치수와 예제 설정은 실물 설치값을 정할 때 참고한다.

함수 분석에 사용한 GitHub 원문은 확인한 커밋으로 링크를 고정했다. Isaac Sim 예제는 2026년 9월 26일 확인한 공식 문서를 기준으로 한다.

코드를 읽는 데 필요한 용어는 다음과 같다.

- **BDDL:** 물체 종류, 배치 영역, 시작·목표 조건을 적는 작업 명세 파일.
- **URDF / Xacro / USD:** URDF는 로봇의 링크·관절·형상을 기술하는 파일, Xacro는 이를 변수와 매크로로 작성하는 형식, USD는 Isaac Sim이 사용하는 장면 형식이다.
- **환경 래퍼 / offscreen:** 래퍼는 환경 생성·초기화·관측을 편하게 호출하도록 감싼 코드다. offscreen은 화면 창을 띄우지 않고 관측 이미지를 만드는 방식이다.
- **상태와 방향 표현:** 상태는 로봇의 위치·방향·그리퍼 값이다. 방향은 축과 회전량을 담은 축각 3값 또는 쿼터니언 4값으로 표현할 수 있어, 정책마다 요구하는 형식을 맞춰야 한다.

표의 `__init__()`는 처음 환경을 만들 때의 설정, `reset()`은 시작 상태로 초기화하는 함수다. 각 표는 **함수의 역할 → 실제 환경에 적용할 부분** 순서로 읽으면 된다. 아래 코드는 연결한 원문에서 설명에 필요한 부분만 발췌했다. 들여쓰기·줄바꿈을 정리하고, 생략한 부분은 주석으로 표시했다.

#### BDDL: 시뮬레이터의 작업 명세서

BDDL은 **시뮬레이터가 읽는 작업 명세서**다. 정식 이름은 *Behavior Domain Definition Language*이며, 물체와 배치 영역, 초기 조건, 목표 조건을 정해 작업을 표현한다. [BDDL 공식 설명](https://github.com/embodied-agent-interface/bddl)

예를 들어 “블록을 상자 안으로 옮기기”는 다음과 같이 정리할 수 있다.

| 항목 | 명세에 적는 내용 |
| --- | --- |
| 물체 | 블록, 상자, 작업대 |
| 배치 영역 | 블록과 상자를 놓을 위치·범위 |
| 초기 조건 | 블록이 작업대 위에 놓여 있음 |
| 목표 조건 | 블록이 상자 안에 들어가면 성공 |

LIBERO는 `.bddl` 파일을 읽어 장면의 물체·배치 조건을 구성하고 목표 달성 여부를 판단한다. 실제로 어떤 이동 동작을 실행할지는 정책이 영상과 로봇 상태를 보고 결정한다. [LIBERO 작업 생성 문서](https://lifelong-robot-learning.github.io/LIBERO/html/procedural_generation/task_generation.html)

이번 연구에서는 task마다 BDDL을 작성해 시뮬레이션의 물체·초기 배치·목표를 정하고, 같은 조건을 실물 task 명세에도 기록한다. 실제 파일 작성과 반영 방법은 3절의 ‘Task별 BDDL 작성과 실물 배치 반영’에서 설명한다.

#### LIBERO: tabletop 장면

[`libero_tabletop_manipulation.py`](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/problems/libero_tabletop_manipulation.py)의 `Libero_Tabletop_Manipulation`이 장면 조건을 정하고, 부모 클래스인 [`BDDLBaseDomain`](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/bddl_base_domain.py)이 로봇·작업대·물체를 결합한다.

작업대의 치수를 정하는 부분과, 그 치수로 베이스 위치를 계산하는 부분이다. 두 코드가 연결되므로 작업대·베이스의 상대 배치를 함께 읽어야 한다.

```python
# __init__()의 기본 작업대 설정
self.table_full_size = (1.0, 1.2, 0.05)
self.table_offset = (0, 0, 0.90)
kwargs.update({"workspace_offset": self.table_offset})
kwargs.update({"arena_type": "table"})

# _load_model()의 로봇 베이스 배치
xpos = self.robots[0].robot_model.base_xpos_offset["table"](
    self.table_full_size[0]
)
self.robots[0].robot_model.set_base_xpos(xpos)
```

| 주요 함수 | 코드에서 하는 일 | 실물 환경 구성에 활용할 부분 |
| --- | --- | --- |
| `Libero_Tabletop_Manipulation.__init__()` | 기본 작업대 크기 `(1.0, 1.2, 0.05) m`, 위치 기준 `table_offset=(0, 0, 0.90) m`와 장면 XML을 지정한다. 로봇 이름에 `Mounted`를 붙여 고정형 모델을 선택한다. | 시뮬레이션의 작업면·베이스 관계를 읽는 출발점이다. 이 치수를 Mirobot 작업종이 크기와 구분해 비례식에 사용할 영역을 정한다. |
| `BDDLBaseDomain._load_model()` | 작업대 크기로 로봇 베이스 위치를 계산하고 `set_base_xpos()`에 전달한다. `TableArena`를 만든 뒤 카메라·물체를 불러와 `ManipulationTask`로 묶는다. | 작업대 크기를 바꾸면 베이스 위치도 확인해야 한다. 실제 생성된 두 위치의 상대 좌표를 배치 기준으로 저장한다. |
| `_load_fixtures_in_arena()` · `_load_objects_in_arena()` · `_load_sites_in_arena()` | BDDL의 고정물·이동 물체를 등록된 모델로 생성하고, 영역의 범위에서 중심·크기를 계산해 site를 만든다. | 기본 작업 영역과 task별 물체를 나누어 설정한다. 물체 종류는 등록 모델, 배치 영역은 BDDL에서 수정한다. |
| `_setup_camera()` | `set_camera()`로 `agentview`·`frontview`·`galleryview`의 위치와 쿼터니언을 지정한다. | 고정 카메라의 관측 방향을 읽고 수정할 위치다. 손목 카메라 장착 변환은 로봇 모델에서 따로 확인한다. |

#### LIBERO: 환경 래퍼

[`env_wrapper.py`](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/env_wrapper.py)는 장면 설정을 실행 가능한 환경으로 연결하고 초기 상태를 복원한다.

위쪽은 창 없이 영상을 만드는 설정이고, 아래쪽은 저장 상태를 복원한 뒤 그 상태에 맞는 관측까지 갱신하는 코드다.

```python
# OffScreenRenderEnv.__init__()
kwargs["has_renderer"] = False
kwargs["has_offscreen_renderer"] = True
super().__init__(**kwargs)

# ControlEnv의 상태 복원 함수
def set_init_state(self, init_state):
    return self.regenerate_obs_from_state(init_state)

def regenerate_obs_from_state(self, mujoco_state):
    self.set_state(mujoco_state)
    self.env.sim.forward()
    self.check_success()
    self._post_process()
    self._update_observables(force=True)
    return self.env._get_observations()
```

| 주요 함수 | 코드에서 하는 일 | 적용할 때의 핵심 |
| --- | --- | --- |
| `ControlEnv.__init__()` | BDDL의 문제 이름에 맞는 환경을 `TASK_MAPPING`에서 찾고, `load_controller_config()`로 읽은 제어 설정을 전달한다. 기본값은 Panda, 말단 위치·방향 제어인 `OSC_POSE`, 초당 20회 제어, 두 카메라의 128×128 영상이다. | 로봇·제어 주기·카메라 이름과 해상도를 연결하는 위치다. 아래 정책 예제는 해상도를 256×256으로 바꾼다. |
| `OffScreenRenderEnv.__init__()` | 화면 창 렌더링을 끄고 offscreen 렌더링을 켠 뒤 `ControlEnv`를 생성한다. | 서버에서 영상 관측을 얻는 진입점이다. 장면 자체의 치수·카메라 위치는 앞의 장면 코드가 정한다. |
| `reset()` · `seed()` | 내부 환경을 초기화하고, 배치 샘플링 오류가 발생하면 초기화를 재시도한다. `seed()`는 난수 설정을 전달한다. | 같은 배치의 재현에는 seed와 함께 사용할 장면·저장 상태를 관리한다. 매번 `reset()`만 호출해 같은 배치가 된다고 가정하지 않는다. |
| `get_sim_state()` · `set_init_state()` → `regenerate_obs_from_state()` | 시뮬레이터 상태를 배열로 얻거나 복원한다. 복원 후 `sim.forward()`와 관측 갱신을 수행해 새 관측을 반환한다. | 확정한 시뮬레이션 시작 상태를 재사용하는 경로다. 이 배열은 해당 시뮬레이션 모델용이며, 실물 Mirobot에는 별도의 `q_start`와 보정값을 저장한다. |

#### RoboCasa: `create_env()`

[`env_utils.py`](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/utils/env_utils.py)의 `create_env()`는 로봇·카메라·주방 장면 인자를 모아 등록된 환경을 생성한다. 여기서 layout은 설비 배치, style은 외관, split은 사용할 장면·물체 집합의 구분이다.

`env_kwargs`에 로봇·카메라 설정을 모아 `robosuite.make()`로 넘긴다. 이 코드가 장면을 직접 그리는 대신 등록된 환경을 생성한다는 점이 비교 근거다.

```python
env_kwargs = dict(
    env_name=env_name,
    robots=robots,
    controller_configs=controller_config,
    camera_names=camera_names,
    camera_widths=camera_widths,
    camera_heights=camera_heights,
    has_renderer=render_onscreen,
    has_offscreen_renderer=(not render_onscreen),
    # 중간 인자 생략
    use_camera_obs=(not render_onscreen),
    # 나머지 장면·물체 인자 생략
)
env = robosuite.make(**env_kwargs)
return env
```

| 주요 함수·처리 | 코드에서 하는 일 | 적용할 때의 핵심 |
| --- | --- | --- |
| `create_env()`의 입력 구성 | `env_name`, 로봇, 카메라 이름·해상도, seed, 주방 layout/style을 받는다. 확인한 버전은 `PandaOmron`과 외부 두 대·손목 한 대의 카메라를 기본으로 둔다. | 고정 탁상 실험에는 사용할 로봇·장면·카메라를 명시해야 한다. 카메라 이름 지정과 설치 위치·보정값 설정은 별도다. |
| `load_composite_controller_config()` · `split` 분기 | 로봇의 복합 제어 설정을 불러온다. `split`에 따라 물체 집합과 layout/style 범위를 바꾸고, `randomize_cameras` 등 관측 조건을 구성한다. | 같은 기본 환경을 유지하려면 layout/style과 무작위화 조건을 고정한다. `split=None`만으로 배치가 고정되지는 않는다. |
| `robosuite.make(**env_kwargs)` | 조합한 인자로 환경을 생성해 반환한다. `render_onscreen=False`일 때 offscreen 렌더링과 카메라 관측을 켠다. 초기화는 호출하는 쪽에서 수행한다. | 이번 범위에서는 사용할 탁상 장면·카메라·초기 조건을 정해야 한다. Mirobot 자체를 시뮬레이션에 재현할 경우 로봇 모델도 추가해야 한다. |

#### Isaac Sim: 공식 URDF 가져오기 예제

[공식 Python 예제](https://docs.isaacsim.omniverse.nvidia.com/latest/importer_exporter/import_urdf.html)는 URDF를 USD 장면으로 변환해 여는 과정을 보여준다. 예제의 UR10 경로를 Mirobot 모델 경로로 바꾼 뒤, 작업대와 관측 구성을 추가하는 방식이다.

`URDFImporterConfig`로 변환 조건을 정하고, `import_urdf()`의 결과를 장면으로 연다. 아래 발췌는 모델 가져오기까지의 범위를 보여준다.

```python
importer = URDFImporter(
    URDFImporterConfig(
        # 원문의 입력 URDF·출력 경로 인자 생략
        merge_mesh=True,
        allow_self_collision=True,
    )
)
output_path = importer.import_urdf()
# 출력 경로 출력문 생략
result, stage = stage_utils.open_stage(output_path)
```

| 주요 함수·설정 | 코드에서 하는 일 | 적용할 때의 핵심 |
| --- | --- | --- |
| `get_extension_manager()` → `get_extension_path()` | URDF importer 확장의 설치 경로를 찾아 예제 모델 경로를 구성한다. | 준비한 Mirobot URDF와 mesh가 실제로 해석되는 경로를 지정한다. |
| `URDFImporterConfig(...)` · `URDFImporter(config)` | 입력·출력 경로와 변환 옵션을 정해 importer를 만든다. 예제는 `merge_mesh=True`, `allow_self_collision=True`를 지정한다. | 두 값은 예제의 선택값이다. Mirobot의 충돌 형상·베이스 고정·관절 구동 설정에 맞춰 검토한다. |
| `import_urdf()` → `stage_utils.open_stage()` | 변환 결과의 경로를 반환하고 해당 USD를 연다. | 이후 작업대·물체·카메라·초기 상태와 관측·동작 연결을 구현해야 한다. 모델을 불러온 단계만으로 실험 환경이 완성되지는 않는다. |

#### Mirobot Gazebo: `mirobot_bringup_moveit.launch`

이 파일은 XML의 `include`로 다른 설정 파일을 불러오고, `node`로 프로그램을 실행한다. ROS는 프로그램 사이의 통신을 연결하고, Gazebo는 물리 시뮬레이션, MoveIt은 로봇 경로 계획, RViz는 상태·경로 시각화를 담당한다. [상위 launch](https://github.com/wlkata/RosForMirobot-master/blob/8a60a4ce16186ddbb9393e20bb904cbab61fc884/mirobot_gazebo/launch/mirobot_bringup_moveit.launch)가 포함하는 네 파일을 따라가면 아래 연결을 확인할 수 있다.

상위 파일은 네 설정을 함께 불러온다. 각 파일이 맡은 기능은 바로 아래 표와 같다.

```xml
<launch>
  <include file="$(find mirobot_gazebo)/launch/mirobot_gazebo_world.launch" />
  <include file="$(find mirobot_gazebo)/launch/mirobot_gazebo_states.launch" />
  <include file="$(find mirobot_gazebo)/launch/mirobot_trajectory_controller.launch" />
  <include file="$(find mirobot_moveit_config)/launch/moveit_planning_execution.launch" />
</launch>
```

| 포함 파일 | 내부 설정·노드의 역할 | 적용할 때의 핵심 |
| --- | --- | --- |
| [`mirobot_gazebo_world.launch`](https://github.com/wlkata/RosForMirobot-master/blob/8a60a4ce16186ddbb9393e20bb904cbab61fc884/mirobot_gazebo/launch/mirobot_gazebo_world.launch) | `empty_world.launch`로 Gazebo를 열고, Xacro를 `robot_description`에 넣는다. `gazebo_ros/spawn_model`이 Mirobot 모델을 생성한다. | 기본은 빈 월드이므로 작업대·물체 배치를 추가해야 한다. 실물 전송용 `mirobot_write_node`는 주석 처리돼 있다. |
| [`mirobot_gazebo_states.launch`](https://github.com/wlkata/RosForMirobot-master/blob/8a60a4ce16186ddbb9393e20bb904cbab61fc884/mirobot_gazebo/launch/mirobot_gazebo_states.launch) | `controller_manager/spawner`로 관절 상태 제어기를 시작한다. `robot_state_publisher`가 `/mirobot/joint_states`를 받아 링크 사이의 좌표 관계인 TF를 발행한다. | 관절 상태와 링크 좌표의 연결을 제공한다. 카메라 영상과 정책 입력 상태를 만드는 처리는 따로 필요하다. |
| [`mirobot_trajectory_controller.launch`](https://github.com/wlkata/RosForMirobot-master/blob/8a60a4ce16186ddbb9393e20bb904cbab61fc884/mirobot_gazebo/launch/mirobot_trajectory_controller.launch) | YAML의 `position_controllers/JointTrajectoryController`를 읽어 `joint1`~`joint6`의 `arm_joint_controller`를 시작한다. | 6축 관절 궤적을 실행하는 구성이다. 정책의 말단 동작을 관절 목표로 바꾸는 변환은 추가해야 한다. |
| [`moveit_planning_execution.launch`](https://github.com/wlkata/RosForMirobot-master/blob/8a60a4ce16186ddbb9393e20bb904cbab61fc884/mirobot_moveit_config/launch/moveit_planning_execution.launch) | 경로 계획 프로그램인 `move_group`과 RViz를 띄운다. 계획한 관절 궤적을 `FollowJointTrajectory` 인터페이스로 Gazebo의 `mirobot/arm_joint_controller`에 전달한다. | 경로 계획·가상 관절 제어를 참고할 수 있다. 실제 로봇 통신·그리퍼 제어는 별도로 연결해야 한다. |

**코드에서 확인한 제약은 세 가지다.** 첫째, ROS 1·Gazebo Classic 구성이다. README의 기본 설치 예시는 ROS Kinetic이고 Noetic으로 이름을 바꾸는 예시도 있지만, 실행에 사용할 ROS·Gazebo·MoveIt 버전 조합은 고정돼 있지 않다. 특히 `mirobot_gazebo/package.xml`에는 실행 시 필요한 의존성이 충분히 선언돼 있지 않아 설치 목록을 보완해야 한다. Gazebo Classic은 2025년 1월 지원이 종료돼, 이 코드를 채택하려면 기존 환경을 고정해 재현하거나 지원되는 구성으로 옮기는 작업이 필요하다. [설치 안내](https://github.com/wlkata/RosForMirobot-master/blob/8a60a4ce16186ddbb9393e20bb904cbab61fc884/README.md) · [패키지 정의](https://github.com/wlkata/RosForMirobot-master/blob/8a60a4ce16186ddbb9393e20bb904cbab61fc884/mirobot_gazebo/package.xml) · [Gazebo 지원 안내](https://classic.gazebosim.org/)

둘째, 이 launch가 불러오는 [Mirobot Xacro](https://github.com/wlkata/RosForMirobot-master/blob/8a60a4ce16186ddbb9393e20bb904cbab61fc884/mirobot_urdf_2/urdf/mirobot_urdf_2.xacro)에는 카메라 센서가 없고 [MoveIt 센서 설정](https://github.com/wlkata/RosForMirobot-master/blob/8a60a4ce16186ddbb9393e20bb904cbab61fc884/mirobot_moveit_config/config/sensors_3d.yaml)도 비어 있다. 따라서 고정·손목 카메라, 영상 취득·시간 동기화, 정책 입력 구성을 추가해야 한다. 셋째, 현재 연결은 Gazebo의 6축 제어기까지다. Cosmos Policy의 말단 동작·그리퍼 출력을 실물 명령으로 변환하고 실제 상태를 되읽는 연결이 필요하다. 따라서 이 공개 예제는 **Mirobot의 기구·관절 제어 구조를 확인하는 참고 자료**로 활용한다.

앞에서 정한 **실물 배치와의 대응, 초기 조건의 재현, 정책 관측과의 연결**을 기준으로 LIBERO를 선택한다. 탁상 장면과 시작 상태를 정하는 코드, 두 카메라의 관측을 정책으로 전달하는 예제가 함께 공개돼 있어 이번 기본 환경의 기준으로 삼을 수 있다. Mirobot의 치수·시작 자세·실물 제어는 별도로 맞춘다.

### 환경 설정에서 참고할 코드

다음으로 LIBERO, OpenVLA-OFT, Cosmos Policy의 환경 관련 코드 중 **어느 코드를 기본 환경 구현의 기준으로 삼을지** 비교한다. OpenVLA-OFT와 Cosmos Policy의 LIBERO 실행 코드는 모두 LIBERO의 `OffScreenRenderEnv`를 불러온다. 따라서 세 레퍼런스에서 환경 자체를 정의하는 부분과, 그 환경을 정책에 연결하는 부분의 역할을 구분해 살펴본다. [OpenVLA-OFT 환경 함수](https://github.com/moojink/openvla-oft/blob/e4287e94541f459edc4feabc4e181f537cd569a8/experiments/robot/libero/libero_utils.py) · [Cosmos Policy 환경 함수](https://github.com/NVlabs/cosmos-policy/blob/18a2accadf4e7a3531e56754102af5a24d2316da/cosmos_policy/experiments/robot/libero/libero_utils.py)

| 레퍼런스 | 환경 관련 구현 | 장점 | 한계와 적용 범위 |
| --- | --- | --- | --- |
| [LIBERO](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/problems/libero_tabletop_manipulation.py) · [환경 생성 코드](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/env_wrapper.py) | 작업대·로봇·카메라 설정, BDDL 로딩, 초기화·상태 복원 | 기본 환경을 구성하는 설정을 직접 확인하고 바꿀 수 있다. | Panda 설정을 Mirobot 실측값과 대응시켜야 한다. **custom 기본 환경 구현의 기준으로 채택한다.** |
| [OpenVLA-OFT](https://github.com/moojink/openvla-oft/blob/e4287e94541f459edc4feabc4e181f537cd569a8/experiments/robot/libero/libero_utils.py) | `get_libero_env()`에서 LIBERO 환경 생성, 관측 영상·상태 전처리 | LIBERO 장면을 정책 입력으로 연결하는 실행 예를 확인할 수 있다. | 작업대·로봇의 정의는 LIBERO에 의존한다. 영상 180° 회전·축각 상태는 OpenVLA-OFT에 맞춘 처리이므로 환경 호출 방식만 참고한다. |
| [Cosmos Policy](https://github.com/NVlabs/cosmos-policy/blob/18a2accadf4e7a3531e56754102af5a24d2316da/cosmos_policy/experiments/robot/libero/libero_utils.py) · [관측 구성 코드](https://github.com/NVlabs/cosmos-policy/blob/18a2accadf4e7a3531e56754102af5a24d2316da/cosmos_policy/experiments/robot/libero/run_libero_eval.py) | LIBERO 환경 생성, 고정·손목 영상과 9차원 상태 구성 | 사용할 Cosmos Policy에 필요한 관측 항목과 처리 과정을 확인할 수 있다. | 작업대·로봇의 정의는 LIBERO에 의존한다. 환경 설정은 LIBERO에서 수정하고, 이 코드는 정책 입력 연결의 기준으로 사용한다. |

![LIBERO 논문의 장면과 작업 생성 절차](images/reference_libero_generation.png)

**LIBERO의 환경 구성 절차.** 장면 선택에서 물체·배치와 초기·목표 조건 정의로 이어진다. 원논문의 개념도이며, 앞에서 분석한 현재 코드에서는 BDDL로 작업 조건을 읽는다. 출처: [LIBERO 논문 Figure 2](https://arxiv.org/abs/2306.03310).

#### 환경 생성과 정책 입력을 연결하는 함수

LIBERO의 장면 생성·초기화·상태 복원은 앞에서 분석한 함수가 담당한다. 여기서는 같은 환경을 각 정책의 입력에 맞추는 함수를 비교한다.

**OpenVLA-OFT — 환경 호출과 전처리 예제**

![OpenVLA-OFT 논문에서 사용한 LIBERO 환경](images/reference_openvla_oft.jpeg)

**OpenVLA-OFT 논문의 LIBERO 장면.** 공간 배치·물체·목표·작업 순서가 다른 네 작업군을 보여준다. LIBERO가 정의한 장면을 불러와 정책에 연결하는 예제로 참고한다. 출처: [OpenVLA-OFT 논문 Figure 3](https://arxiv.org/html/2502.19645v1).

`[::-1, ::-1]`은 영상의 행·열을 모두 뒤집어 180° 회전한다. 상태 배열에서는 위치 다음에 축각, 마지막에 그리퍼 값이 들어간다.

```python
# get_libero_image()의 영상 처리
img = obs["agentview_image"]
img = img[::-1, ::-1]

# prepare_observation()의 상태 구성
observation = {
    # 영상 항목 생략
    "state": np.concatenate(
        (obs["robot0_eef_pos"],
         quat2axisangle(obs["robot0_eef_quat"]),
         obs["robot0_gripper_qpos"])
    ),
}
```

| 주요 함수 | 코드에서 하는 일 | 이번 연구에서 참고할 부분 |
| --- | --- | --- |
| `get_libero_env()` | task의 BDDL 경로로 `OffScreenRenderEnv`를 만들고 해상도 기본값 256을 전달한다. `env.seed(0)`을 호출한 뒤 환경과 작업 지시문을 반환한다. | 환경을 불러오는 방식과 설정 전달 경로를 참고한다. 작업대·베이스 배치는 LIBERO 장면 코드가 정의한다. |
| `get_libero_image()` · `get_libero_wrist_image()` | 고정·손목 관측을 읽고 `img[::-1, ::-1]`로 두 영상을 180° 회전한다. | OFT 학습 영상에 맞춘 처리이므로, 사용할 Cosmos의 처리와 구분한다. |
| `prepare_observation()` · `quat2axisangle()` | 영상을 입력 크기로 바꾸고 상태를 **말단 위치 3 + 축각 3 + 그리퍼 관절 2 = 8차원**으로 구성한다. 쿼터니언은 회전벡터로 변환한다. | 상태의 순서·회전 표현을 비교하는 근거다. 이 8차원 구성을 Cosmos 입력에 그대로 사용하지 않는다. |
| `run_episode()` | `reset()` 후 저장된 초기 상태를 적용하고, 기본 10회의 대기 동작 뒤 관측·동작 반복을 시작한다. 대기 횟수는 설정 가능하다. | 시뮬레이션 초기화 흐름을 참고한다. 실물에서는 검증한 시작 자세 복귀와 상태 확인 절차로 구성한다. |

[OpenVLA-OFT 환경·영상 함수](https://github.com/moojink/openvla-oft/blob/e4287e94541f459edc4feabc4e181f537cd569a8/experiments/robot/libero/libero_utils.py) · [관측 구성·에피소드 실행](https://github.com/moojink/openvla-oft/blob/e4287e94541f459edc4feabc4e181f537cd569a8/experiments/robot/libero/run_libero_eval.py)

**Cosmos Policy-LIBERO — 최종 관측 연결의 기준**

![NVIDIA가 공개한 Cosmos Policy-LIBERO의 손목·고정 관측과 미래 영상 예측](images/reference_cosmos_policy_libero.png)

**Cosmos Policy-LIBERO의 관측과 미래 영상 예측.** NVIDIA 공식 LIBERO-Spatial 시연 영상에서 추출한 화면이다. 왼쪽부터 손목 관측·손목 미래 예측·고정 카메라 관측·고정 카메라 미래 예측을 보여준다. 화면의 `real`은 LIBERO 시뮬레이터에서 얻은 관측을 뜻한다. 출처: [공식 LIBERO 시연](https://research.nvidia.com/labs/cosmos-lab/cosmos-policy/).

이 연구는 **`nvidia/Cosmos-Policy-LIBERO-Predict2-2B`**의 고정·손목 두 영상과 **9차원 로봇 상태**를 입력으로 사용한다. 출력은 단계마다 말단 위치·회전 변화량 6값과 그리퍼 명령 1값을 갖는 **16단계 동작 청크**다. 이 7값은 Panda의 7개 관절각을 뜻하지 않으며, Mirobot에서는 아래의 말단 제어·역기구학 연결을 적용한다. [LIBERO 모델 카드](https://huggingface.co/nvidia/Cosmos-Policy-LIBERO-Predict2-2B) · [LIBERO 관측·평가 코드](https://github.com/NVlabs/cosmos-policy/blob/18a2accadf4e7a3531e56754102af5a24d2316da/cosmos_policy/experiments/robot/libero/run_libero_eval.py)

두 함수의 핵심 부분을 나란히 발췌했다. `np.flipud()`는 상하만 반전하며, `proprio`의 배열 순서는 그리퍼·위치·쿼터니언이다. OFT와 달라지는 부분을 코드에서 직접 확인할 수 있다.

```python
# get_libero_image()의 영상 처리
img = obs["agentview_image"]
if flip_images:
    img = np.flipud(img)

# prepare_observation()의 관측 구성
observation = {
    "primary_image": img,
    "wrist_image": wrist_img,
    "proprio": np.concatenate(
        (obs["robot0_gripper_qpos"],
         obs["robot0_eef_pos"],
         obs["robot0_eef_quat"])
    ),
}
```

| 주요 함수 | 코드에서 하는 일 | 이번 연구에서 적용할 부분 |
| --- | --- | --- |
| `get_libero_env()` | BDDL·해상도를 `OffScreenRenderEnv`에 전달하고 `env.seed(0)`을 설정한다. 기본 해상도는 256이다. | LIBERO custom 환경을 생성하는 진입점으로 사용한다. |
| `get_libero_image()` · `get_libero_wrist_image()` | `flip_images=True`이면 `np.flipud()`로 상하 반전한다. 함수의 기본값은 False지만 평가 설정은 기본 True를 전달한다. | 저장·학습·추론 영상의 방향을 통일한다. 실물 카메라는 원본 방향을 확인해 필요한 변환을 정한다. |
| `prepare_observation()` | `primary_image`, `wrist_image`, `proprio`를 만든다. 상태 순서는 **그리퍼 2 → 말단 위치 3 → 쿼터니언 4 = 9차원**이며, 이 함수는 쿼터니언을 축각으로 바꾸지 않는다. | Mirobot 기록기와 입력 변환기를 이 항목·순서에 맞춘다. 좌표계·단위·그리퍼 값의 의미도 함께 맞춘다. |
| `run_episode()` | 초기화와 저장 상태 복원 후 코드에 지정된 10회의 대기 동작을 수행하고 정책 실행을 시작한다. | LIBERO의 초기화 절차로 참고한다. 실물에는 해당 동작을 그대로 보내지 않고 복귀 완료와 새 관측을 확인한 뒤 추론한다. |

[Cosmos 환경·영상 함수](https://github.com/NVlabs/cosmos-policy/blob/18a2accadf4e7a3531e56754102af5a24d2316da/cosmos_policy/experiments/robot/libero/libero_utils.py) · [관측 구성·에피소드 실행](https://github.com/NVlabs/cosmos-policy/blob/18a2accadf4e7a3531e56754102af5a24d2316da/cosmos_policy/experiments/robot/libero/run_libero_eval.py)

핵심 차이는 **영상 방향과 상태 표현**이다. Cosmos의 `proprio`는 로봇 상태 입력을 뜻한다. 같은 LIBERO 환경을 쓰더라도 OFT의 전처리를 복사하면 Cosmos가 기대하는 영상 방향·상태 순서와 달라질 수 있으므로, 최종 입력 변환은 선택한 Cosmos Policy 코드에 맞춘다.

이 비교에서 사용할 코드의 역할이 정리된다. **작업대·로봇·카메라·초기 상태는 LIBERO 코드에서 설정하고, 영상과 로봇 상태를 정책 입력으로 만드는 부분은 Cosmos Policy-LIBERO 코드를 따른다.**

### 최종 사용할 환경과 설정 방법

위 비교에 따라 **LIBERO의 `Libero_Tabletop_Manipulation`을 바탕으로 한 custom 환경**을 사용한다. 테이블 위에 단일 로봇 팔을 고정하고, 작업 영역을 보는 `agentview`와 손목에 달린 `robot0_eye_in_hand` 카메라를 둔다. 이 환경에서 작업대·카메라·시작 자세를 정해 실물 배치의 기준으로 삼는다. [LIBERO tabletop 코드](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/problems/libero_tabletop_manipulation.py)

이 초기 환경을 선택한 구체적인 근거는 다음과 같다.

- **실제 작업대와 대응하는 구조다.** 현재 Mirobot은 책상에 고정한 단일 팔로 격자 작업판을 사용한다. LIBERO의 `__init__()`와 `_load_model()`에는 작업대와 로봇 베이스의 상대 위치가 정의돼 있어, 사용할 영역의 폭·깊이·중심을 실측한 뒤 배치 비율을 계산할 수 있다. 검토한 RoboCasa의 주방 구성과 비교하면 이번 탁상 환경에 필요한 설정을 직접 확인하기 쉽다.
- **두 카메라의 역할을 분명히 정할 수 있다.** `agentview`는 작업 영역과 물체 배치를, `robot0_eye_in_hand`는 그리퍼 주변을 관측한다. 실제로 설치할 고정·손목 D405와 대응하고, Cosmos Policy-LIBERO도 이 두 영상을 입력으로 사용하므로 초기 구도와 모델 관측을 같은 기준으로 정할 수 있다.
- **공통 시작 상태를 재현하는 코드가 있다.** `set_init_state()`는 저장된 상태를 복원하고 그 상태의 관측까지 갱신한다. 이를 참고해 실물에서도 TCP 위치·접근 방향·그리퍼 상태를 공통 조건으로 기록한다. Panda와 관절 구조가 다른 Mirobot의 시작 자세는 6축 역기구학과 반복 복귀 확인으로 정하며, 그 구체적인 측정 방법은 3절에서 다룬다.

[작업대·카메라 설정](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/problems/libero_tabletop_manipulation.py) · [초기 상태 복원](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/env_wrapper.py) · [Cosmos Policy-LIBERO 관측 구성](https://github.com/NVlabs/cosmos-policy/blob/18a2accadf4e7a3531e56754102af5a24d2316da/cosmos_policy/experiments/robot/libero/run_libero_eval.py)

문서에서 **Cosmos Policy-LIBERO**는 이 LIBERO 환경을 Cosmos Policy 공식 코드로 실행·연결하는 구성을 뜻한다. LIBERO가 장면과 작업을 정의하고, robosuite·MuJoCo가 제어와 물리 시뮬레이션을 처리하며, Cosmos Policy가 관측으로부터 동작을 예측한다.

LIBERO 환경을 불러오는 기본 형태는 아래와 같다. `custom_scene.bddl`은 앞으로 작성할 장면 파일이며, 코드는 환경 설정 방식을 설명하는 예시다.

```python
from libero.libero.envs import OffScreenRenderEnv

env = OffScreenRenderEnv(
    bddl_file_name="custom/custom_scene.bddl",
    camera_names=["agentview", "robot0_eye_in_hand"],
    camera_heights=256,
    camera_widths=256,
)
```

작업대와 고정 카메라는 tabletop 장면 코드에서, 손목 카메라는 로봇 모델에서, 시작 관절각은 초기화 설정에서 정한다. Task별 물체·배치·목표는 BDDL로 관리한다. 따라서 로봇 모델 교체와 task 변경은 아래처럼 각각 연결한다.

### LIBERO tabletop의 Panda를 Mirobot 모델로 연결하는 방법

tabletop 코드가 로봇의 모든 정보를 직접 담는 구조는 아니다. **환경에 전달한 로봇 이름으로 모델 클래스를 찾고, 그 클래스가 로봇 XML·초기 관절각·그리퍼 정보를 불러온다.** 확인한 LIBERO 버전에서는 `robots=["Panda"]`를 tabletop 내부에서 `MountedPanda`로 바꾼다. 따라서 동일한 구조로 Mirobot을 연결하려면 `MountedMirobot` 모델을 준비하고 등록해야 한다. [LIBERO tabletop](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/problems/libero_tabletop_manipulation.py#L20-L22)

아래는 현재 코드에서 로봇이 선택되고 XML이 불러와지는 핵심 부분이다. 서로 다른 파일의 관련 줄만 발췌했다.

```python
# env_wrapper.py — 기본 로봇 이름
robots=["Panda"]

# libero_tabletop_manipulation.py — tabletop용 모델 이름으로 변환
kwargs.update({"robots": [f"Mounted{robot_name}" for robot_name in kwargs["robots"]]})

# robots/mounted_panda.py — 해당 모델이 Panda XML을 읽음
super().__init__(xml_path_completion("robots/panda/robot.xml"), idn=idn)
```

호출 순서는 다음과 같다.

```text
OffScreenRenderEnv(robots=["Panda"])
 → ControlEnv: BDDL의 문제 이름으로 tabletop 환경 선택
 → Libero_Tabletop_Manipulation: "Panda" → "MountedPanda"
 → BDDLBaseDomain → SingleArmEnv → RobotEnv._load_robots()
 → ROBOT_CLASS_MAPPING["MountedPanda"]로 SingleArm 생성
 → SingleArm.load_model() → Robot.load_model() → create_robot("MountedPanda")
 → MountedPanda가 robot.xml 로딩
 → BDDLBaseDomain._load_model()이 작업대·로봇·물체 결합
```

[환경 래퍼](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/env_wrapper.py) · [LIBERO 로봇 등록](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/robots/__init__.py) · [로봇 생성](https://github.com/ARISE-Initiative/robosuite/blob/v1.4.0/robosuite/environments/robot_env.py#L529-L538) · [모델 로딩](https://github.com/ARISE-Initiative/robosuite/blob/v1.4.0/robosuite/robots/robot.py#L81-L94)

#### Mirobot으로 바꾸는 순서

**1. 실제 기구와 일치하는 MuJoCo 모델을 준비한다.** WLKATA의 URDF에서 링크 길이, 6개 관절의 축·원점·가동 범위, 메시와 관성을 확인한다. 이를 MuJoCo의 MJCF XML로 옮기고 실제 그리퍼와 D405 장착부를 반영한다. MuJoCo 자체에는 URDF 읽기 기능이 있지만, robosuite의 `ManipulatorModel`은 MJCF의 body·joint·actuator·site 구조를 읽으므로 XML 경로만 URDF로 바꿔 연결할 수는 없다. 기본 `SingleArm` 제어를 사용할 경우 팔의 actuator는 해당 제어기의 토크 출력을 받는 구성이어야 한다. [WLKATA 모델](https://github.com/wlkata/Wlkata_Mirobot_Ros2) · [MuJoCo 모델 형식](https://mujoco.readthedocs.io/en/stable/modeling.html#urdf-extensions) · [ManipulatorModel](https://github.com/ARISE-Initiative/robosuite/blob/v1.4.0/robosuite/models/robots/manipulators/manipulator_model.py) · [SingleArm 제어](https://github.com/ARISE-Initiative/robosuite/blob/v1.4.0/robosuite/robots/single_arm.py#L193-L232)

**2. `MountedMirobot` 모델 클래스의 정보를 정한다.** `MountedPanda`를 구조 참고로 삼되, 아래 항목을 Mirobot 값으로 정의한다. `init_qpos`에는 앞에서 정한 실물 시작 자세의 **6개 관절각을 라디안으로** 넣는다. 관절 순서·회전 부호·영점은 MJCF와 실제 SDK 사이에서 대응시킨다. SDK의 Homing 각도 0이 각 MJCF 관절의 0과 같다고 가정하지 않는다.

| 모델 속성·구성 | Mirobot에서 정의할 내용 |
|---|---|
| `__init__()`의 XML 경로 | 변환·검증한 Mirobot MJCF와 메시 경로 |
| `init_qpos` | 실물 시작 자세에 대응하는 6개 관절각. 최종 값은 실측·SDK 확인 필요 |
| `default_mount` · `base_xpos_offset["table"]` | 실제 받침대와 작업대에 대한 베이스 위치. Panda의 `RethinkMount`·베이스 오프셋을 그대로 사용하지 않음 |
| `default_gripper` · `arm_type` | 등록한 Mirobot 그리퍼 이름과 `"single"` |
| `_eef_name` 및 그리퍼 site | 도구 부착 body와 실제 TCP에 맞춘 `grip_site` 등 관측·제어 기준 |
| `default_controller_config` · 기구 범위 속성 | Mirobot에 맞는 제어 설정, `top_offset`, `_horizontal_radius` |

그리퍼 클래스에는 초기 손가락 위치와 `format_action()`의 개폐 변환을 정의하고, XML에 제어·관측에서 참조하는 site와 센서를 둔다. `SingleArm`은 `grip_site`, `grip_cylinder`, 말단 힘·토크 센서 이름도 참조하므로 외형만 비슷한 그리퍼 XML로는 충분하지 않다. [MountedPanda 속성](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/robots/mounted_panda.py) · [GripperModel](https://github.com/ARISE-Initiative/robosuite/blob/v1.4.0/robosuite/models/grippers/gripper_model.py)

**3. 환경을 만들기 전에 모델과 제어 클래스를 등록한다.** `ManipulatorModel`을 상속한 `MountedMirobot` 클래스는 import할 때 robosuite의 모델 등록표에 자동 등록된다. 별도로 `ROBOT_CLASS_MAPPING["MountedMirobot"] = SingleArm`을 추가하고, 그리퍼도 `GRIPPER_MAPPING`에 등록한다. 새 모듈을 `libero.libero.envs.robots`에서 import하도록 연결하면 tabletop이 해당 모델을 찾을 수 있다. 준비할 파일은 Mirobot MJCF·메시, `mounted_mirobot.py`, 그리퍼 XML·클래스, 등록 코드이며 필요하면 받침대 모델과 제어 설정을 추가한다. 이 파일들은 구현할 대상이며, 현재 문서에 완성된 Mirobot 시뮬레이터가 포함된 것은 아니다. [모델 자동 등록](https://github.com/ARISE-Initiative/robosuite/blob/v1.4.0/robosuite/models/robots/robot_model.py#L6-L45) · [제어 클래스 등록표](https://github.com/ARISE-Initiative/robosuite/blob/v1.4.0/robosuite/robots/__init__.py) · [그리퍼 등록표](https://github.com/ARISE-Initiative/robosuite/blob/v1.4.0/robosuite/models/grippers/__init__.py)

등록 코드는 다음 형태다. 아래의 새 모듈과 클래스는 위 모델 파일을 작성한 뒤 존재해야 한다.

```python
# libero/libero/envs/robots/__init__.py에 연결할 등록 예시
from robosuite.robots.single_arm import SingleArm
from robosuite.robots import ROBOT_CLASS_MAPPING
from robosuite.models.grippers import GRIPPER_MAPPING
from .mounted_mirobot import MountedMirobot
from .mirobot_gripper import MirobotGripper

ROBOT_CLASS_MAPPING["MountedMirobot"] = SingleArm
GRIPPER_MAPPING["MirobotGripper"] = MirobotGripper
# MountedMirobot.default_gripper도 "MirobotGripper"를 반환하도록 정의
```

**4. 환경 생성 인자와 카메라를 연결한다.** 위 모델 등록과 검증이 끝난 뒤 환경에 `robots=["Mirobot"]`를 전달한다. tabletop이 앞에 `Mounted`를 붙이므로 `robots=["MountedMirobot"]`로 전달하지 않는다. 외부 카메라는 tabletop의 `_setup_camera()`에 실측 위치·방향을 넣고, 손목 카메라는 Mirobot의 말단 body에 이름 `eye_in_hand`로 넣는다. 로봇 0의 접두사가 붙으면 정책이 읽는 `robot0_eye_in_hand_image`가 된다.

3절에서 저장한 D405의 `R_wc, t_wc_mm`을 XML에 넣을 때는 카메라 축도 바꾼다. RealSense는 +Z가 앞·+Y가 아래이고, MuJoCo는 −Z가 앞·+Y가 위다. `R_PW,t_PW_mm`을 **작업종이→카메라가 속한 부모 body** 변환으로 정하면 다음과 같다. 고정 카메라는 world body, 손목 카메라는 말단 body를 부모로 사용한다.

```python
import numpy as np
from robosuite.utils.transform_utils import mat2quat

pos_m = (R_PW @ t_wc_mm + t_PW_mm) / 1000
R_camera = R_PW @ R_wc @ np.diag([1, -1, -1])
quat_xyzw = mat2quat(R_camera)
quat_wxyz = quat_xyzw[[3, 0, 1, 2]]  # MJCF의 quat 순서
```

고정 카메라에는 계산한 `pos_m,quat_wxyz`를 `_setup_camera()`의 `set_camera()`에 넣고, 손목 카메라에는 XML camera의 `pos,quat`로 저장한다. 부모 좌표 변환이 확인되지 않았다면 값은 실측 필요로 둔다. [MuJoCo 카메라 축](https://mujoco.readthedocs.io/en/3.3.2/XMLreference.html#body-camera) · [robosuite 쿼터니언 변환](https://github.com/ARISE-Initiative/robosuite/blob/v1.4.0/robosuite/utils/transform_utils.py)

```python
# 전제: MountedMirobot·그리퍼 모델을 구현하고 import로 등록한 상태
from libero.libero.envs import OffScreenRenderEnv

env = OffScreenRenderEnv(
    bddl_file_name="custom_tasks/move_bowl_to_target.bddl",
    robots=["Mirobot"],
    controller="OSC_POSE",
    initialization_noise=None,
    camera_names=["agentview", "robot0_eye_in_hand"],
    camera_heights=256,
    camera_widths=256,
)
obs = env.reset()
```

이는 **모델 구현 후의 호출 예시**다. 이름만 바꾸면 실행되는 코드는 아니다. `OSC_POSE`의 6차원 말단 명령과 그리퍼 1값을 유지하려면 Mirobot 모델·actuator·제어 범위에 맞게 동작을 검증해야 한다. Cosmos의 `get_libero_env()`는 `env_args`를 `OffScreenRenderEnv`로 전달하므로, 그 인자에도 같은 로봇·카메라 설정을 넣는다. [Cosmos 환경 생성](https://github.com/NVlabs/cosmos-policy/blob/18a2accadf4e7a3531e56754102af5a24d2316da/cosmos_policy/experiments/robot/libero/libero_utils.py)

작업대 치수를 함께 변경할 때는 확인한 tabletop 코드의 `table_full_size` 분기에서 `self.table_full_size = kwargs["table_full_size"]`로 값을 읽도록 바로잡아야 한다. 해당 버전은 정의되지 않은 `table_full_size` 지역 변수를 사용한다. 또한 `table_offset=(0, 0, 0.90)`은 고정값이므로 custom 장면의 작업면 높이에 맞춰 설정한다. 작업종이 643×423 mm는 작업 영역이며 책상 전체 치수와 구분한다. [해당 초기화 코드](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/problems/libero_tabletop_manipulation.py#L10-L24)

**5. Mirobot 상태로 초기화하고 관측을 확인한다.** `reset()` 후 6축 관절 상태, TCP 위치·방향, 그리퍼 상태, 외부·손목 영상이 실측한 시작 상태와 대응하는지 확인한다. 로봇을 바꾸면 MuJoCo 상태 배열의 크기·순서가 달라지므로 기존 Panda 초기 상태 파일을 `set_init_state()`로 재사용하지 않고, 새 환경에서 초기 상태를 다시 저장한다. 관절은 6개여도 말단 위치·방향 명령은 6차원일 수 있다. 따라서 정책 출력 7값을 로봇의 7개 관절각으로 해석하지 않는다. 실물에서는 그 말단 명령을 Mirobot의 역기구학·SDK 명령으로 연결한다. [초기 관절값 적용](https://github.com/ARISE-Initiative/robosuite/blob/v1.4.0/robosuite/robots/robot.py#L104-L132) · [말단·그리퍼 관측](https://github.com/ARISE-Initiative/robosuite/blob/v1.4.0/robosuite/robots/single_arm.py#L258-L302) · [상태 복원](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/env_wrapper.py)

### Cosmos Policy 체크포인트 비교와 최종 선택

**체크포인트는 학습된 모델 가중치를 저장한 파일이다.** 추가 학습의 출발점으로 사용할 체크포인트를 카메라와 동작 형식에 따라 비교한다.

| 체크포인트 | 장점 | 이번 Mirobot 구성에서의 제약 |
| --- | --- | --- |
| **[LIBERO-Predict2-2B](https://huggingface.co/nvidia/Cosmos-Policy-LIBERO-Predict2-2B)** | 고정·손목 두 카메라와 단일 팔의 말단 동작을 사용해 이번 관측·제어 설계와 대응하기 쉽다. | Panda 시뮬레이션 기반이므로 Mirobot 시연 학습과 상태·동작 변환이 필요하다. |
| [RoboCasa-Predict2-2B](https://huggingface.co/nvidia/Cosmos-Policy-RoboCasa-Predict2-2B) | 단일 팔 말단 제어를 사용하며 다양한 주방 조작을 학습했다. | 외부 카메라 두 대와 손목 카메라를 사용해 이번 두 카메라 구성과 차이가 있다. |
| [ALOHA-Predict2-2B](https://huggingface.co/nvidia/Cosmos-Policy-ALOHA-Predict2-2B) | 실물 로봇 시연으로 학습했으며 배포 코드가 공개돼 있다. | 양팔 관절·그리퍼 동작과 세 카메라를 사용해 단일 팔 Mirobot과의 변환 범위가 크다. |
| [ALOHA Planning 모델](https://huggingface.co/nvidia/Cosmos-Policy-ALOHA-Planning-Model-Predict2-2B) | 후보 동작의 미래 상태와 가치를 예측할 수 있다. | ALOHA 정책과 함께 쓰는 보조 모델이므로 이번 동작 정책의 출발점으로 사용하지 않는다. |

추가 학습의 출발 모델은 **LIBERO-Predict2-2B**로 정한다. 선택 근거는 다음 세 가지다.

- **고정·손목 두 영상이 실제 설치 계획과 맞는다.** RoboCasa 모델의 외부 두 대·손목 한 대, ALOHA 모델의 양팔·세 카메라 구성과 비교하면 LIBERO 모델이 이번 단일 팔·두 시점 구성에 더 가깝다.
- **출력을 말단 자세로 연결할 수 있다.** 단계마다 위치·회전 변화량 6값과 그리퍼 명령 1값을 예측하므로, 목표 TCP 자세를 Mirobot의 6축 역기구학에 연결하는 기준을 세울 수 있다. Panda의 7관절과 Mirobot의 6축 차이는 실제 도달 범위와 목표 자세를 확인하는 과정에서 반영한다.
- **선택한 환경과 모델 사이의 연결이 공개돼 있다.** 공식 LIBERO 평가 코드에서 환경 생성, 두 영상의 전처리, 그리퍼·위치·쿼터니언의 9차원 상태 순서를 확인할 수 있다. 초기 환경의 관측이 모델 입력으로 전달되는 과정을 같은 코드에서 검토할 수 있다는 점이 선정 근거다.

**실물 추론에는 이 출발 모델을 Mirobot 시연으로 추가 학습한 체크포인트를 사용한다.** 원본 모델은 Panda 시뮬레이션에서 학습돼 Mirobot의 촬영 영상·그리퍼 상태·동작 분포와 차이가 있다. 따라서 실제 데이터에 맞춘 가중치와 정규화 통계를 실물 추론의 기준으로 정한다. 실물 추론용 체크포인트는 추가 학습 후 생성할 모델이다.

[LIBERO 모델 카드](https://huggingface.co/nvidia/Cosmos-Policy-LIBERO-Predict2-2B) · [공식 LIBERO 환경·영상 함수](https://github.com/NVlabs/cosmos-policy/blob/18a2accadf4e7a3531e56754102af5a24d2316da/cosmos_policy/experiments/robot/libero/libero_utils.py) · [관측·동작 연결 코드](https://github.com/NVlabs/cosmos-policy/blob/18a2accadf4e7a3531e56754102af5a24d2316da/cosmos_policy/experiments/robot/libero/run_libero_eval.py)

## 3. Panda 기준 환경을 Mirobot에 맞추는 방법

먼저 작업대에 Mirobot을 고정하고 고정 카메라와 손목 카메라를 설치한다. 시뮬레이션의 상대 배치와 관측 방향을 참고하되, 거리·높이·시작 자세는 Mirobot의 도달 범위와 카메라 시야에 맞춰 정한다. 이후 **TCP는 그리퍼로 물체를 집는 기준점**, `q_start`는 실험 시작 시 사용할 6개 관절각을 뜻한다. 베이스 좌표계는 로봇 받침을 기준으로, 작업면 좌표계는 작업종이를 기준으로 위치를 나타내는 방법이다.

| 구분 | 실물 설정 | 유지·변경 기준 |
| --- | --- | --- |
| 작업대·로봇 베이스 | 로봇을 고정하고 작업 영역과 기준 좌표계 설정 | task를 바꿔도 유지 |
| 카메라·조명 | 고정 카메라는 전체 작업 영역, 손목 카메라는 집는 부분을 관측 | 위치·방향·영상 전처리와 조명 조건 유지 |
| 공통 시작 조건 | 작업 영역을 가리지 않는 대기 자세와 그리퍼 초기 상태 지정 | 매회 실행 전에 같은 조건으로 복귀 |
| task별 물체 배치 | 대상 물체와 시작·목표 위치, 필요한 주변 물체 배치 | 정해진 작업 영역 안에서 task에 맞춰 변경 |

### 실제 Mirobot 사진을 기준으로 한 구성

아래는 제공받은 실제 Mirobot 환경 사진이다. 로봇 베이스가 사진 오른쪽에 있고, 팔은 왼쪽 격자 작업판 방향으로 뻗어 있으며 그리퍼는 아래를 향한다. 왼쪽에는 원형 판, 앞쪽에는 조작기와 케이블이 놓여 있다. 이 배치를 출발점으로 작업 영역과 공통 시작 자세를 정한다.

![사용자가 제공한 실제 Mirobot 작업대 사진](images/mirobot_real_setup.png)

| 사진에서 확인한 구성 | 이번 실험에서의 설정 |
| --- | --- |
| 오른쪽 로봇 베이스와 왼쪽 격자 작업판 | 베이스의 고정 상태를 확인하고, 그리퍼가 닿는 작업판 영역을 실측해 표시 |
| 아래를 향한 그리퍼와 왼쪽으로 뻗은 팔 | 접근 방향의 참고로 사용하고, 관절 여유와 복귀 경로를 확인해 `q_start`를 별도로 확정 |
| 원형 판과 격자 | 배치 비교용 기준점으로 활용하되 격자 간격과 판의 치수를 실측하고 로봇 좌표계와 연결 |
| 앞쪽 조작기·케이블 | 조작기가 손에 닿도록 두면서, 로봇 이동과 물체 배치를 방해하지 않도록 작업 영역 밖으로 정리 |

사진만으로는 고정 카메라의 설치 상태나 그리퍼 부근 검은 모듈의 기능을 확인할 수 없다. 두 시점의 영상이 실제로 수집되는지 먼저 확인하고, 필요한 카메라를 설치한다. 사진 속 자세도 시작 자세의 후보이며, 반복 복귀가 가능한지 확인한 뒤 사용한다.

![실제 사진을 참고한 Mirobot 기본 배치와 시작 자세 개념도](images/mirobot_setup_concept.png)

**그림은 실제 사진을 참고해 작성한 배치 제안 개념도다.** 왼쪽은 베이스를 유지하면서 작업 영역·카메라·케이블을 정리하는 방법이고, 오른쪽은 그리퍼의 접근 방향과 시작 높이를 정해 6축 시작 자세로 저장하는 과정이다. 주황 점선은 추가 설치 제안이며, 작업 영역·높이·카메라 위치는 실측 후 확정한다. 아래 순서처럼 기본 배치를 고정한 뒤 물체와 task를 정하고, 시연·학습·평가로 이어간다.

### 제공된 실측값과 배치 기준

다음은 사용자가 제공한 실측 기록이다. 높이는 작업종이 표면을 기준으로 하며, 좌우 각도는 Homing 상태를 0°로 두고 `inverse.py`에서 확인한 동작 범위다. 길이 단위는 mm로 통일했다.

| 항목 | 제공값 | 배치에 반영할 때의 기준 |
| --- | --- | --- |
| 작업종이 가로·세로 | **643 × 423 mm** | 작업판 위 위치를 표시할 기준 면적. 실제 로봇이 사용할 영역은 이 안에서 별도로 정한다. |
| 책상 상판 두께 | **25 mm** | 베이스 고정구와 작업대 하부 간섭을 확인할 때 사용한다. 작업종이 기준 높이에 다시 더하지 않는다. |
| Homing 높이 | **300 mm** | 작업종이 표면 기준으로 기록한 Homing 상태의 높이. 측정한 로봇 지점과 TCP의 일치 여부는 TCP 보정에서 확인한다. |
| 최대 높이 | **344 mm** | 작업종이 표면 기준, `inverse.py`에서 확인한 최대 높이. 측정 자세·장착 도구에 해당하는 값으로 사용한다. |
| 왼쪽·오른쪽 최대 각도 | **Homing 0° 기준 각 45°** | `inverse.py`에서 확인한 좌우 동작 범위로 기록한다. 특정 관절의 제조사 한계각이나 모든 자세의 도달 범위로 일반화하지 않는다. |

작업종이의 한 모서리를 원점으로 표시하고 긴 변 방향을 x축, 짧은 변 방향을 y축으로 정하면, 종이의 범위는 `0 ≤ x ≤ 643`, `0 ≤ y ≤ 423 mm`이고 중심은 **`(321.5, 211.5) mm`**다. 이 중심은 종이의 기하학적 중심이며, 로봇 베이스 원점이나 사용할 작업 영역의 중심과는 별도로 기록한다.

현재 사진의 오른쪽 베이스·왼쪽 작업판 배치를 유지하면서, 종이 위에 베이스 장착 기준점과 정면 방향을 먼저 표시한다. 그다음 사용할 접근 방향에서 도달 가능한 영역을 확인해 `x_min, x_max, y_min, y_max`를 정한다. 여기서 네 경계는 도달점 전체를 둘러싼 최솟값·최댓값이 아니라, 사용할 TCP 방향·높이에서 선택한 직사각형 작업 영역의 경계다. 내부에 도달 불가 구역이 있으면 영역을 줄이거나 제외 구역으로 기록하고, 배치점과 이동 경로를 확인한다. 검증 전에는 후보 영역으로 두며, 작업종이·도달 범위·간섭 조건을 충족한 영역의 치수를 아래 비례식에 사용한다.

```text
W_M = x_max − x_min
D_M = y_max − y_min
c_M = ((x_min + x_max)/2, (y_min + y_max)/2)
```

따라서 **종이 전체 크기 643 × 423 mm를 곧바로 Mirobot의 작업 영역으로 대입하지 않는다.** 실제 배율과 설치 좌표를 확정하려면 이 영역의 경계, 종이–베이스 좌표 변환, 선택한 LIBERO custom 환경의 기준 영역 치수가 추가로 필요하다. 위 높이·좌우 각도 조건에서 실제로 도달하는 점을 작업종이에 표시해 경계를 구하고, 사용할 TCP 방향과 물체 높이에서 다시 확인한다. 이때 `inverse.py`의 명령 축·회전 중심·당시 자세도 함께 기록한다.

### 실제로 측정할 길이와 각도

아래 그림의 A~G는 실물 환경을 재현하기 위해 기록할 항목이다. 베이스 기준 원점과 축을 먼저 표시하고, 길이는 mm, 각도는 도 또는 라디안 중 정한 단위로 기록한다. 시뮬레이션·학습 코드에서 다른 단위를 사용하면 입출력 변환 위치를 명시한다. 사진의 격자나 팔 모양으로 수치를 추정하지 않고 실측·보정한 값을 채운다.

![Mirobot 실물 환경의 길이와 각도 측정 항목 A부터 G까지](images/mirobot_measurements.png)

측정 위치를 설명한 개념도이며 실제 로봇의 비율이나 치수를 나타내지는 않는다. 그림의 `|x_c|, |y_c|`는 거리의 크기이고, 좌표를 저장할 때는 실제 베이스 축에 따른 부호까지 기록한다.

| 표시 | 재거나 기록할 길이·각도 | 측정 기준과 방법 |
| --- | --- | --- |
| **A 작업 영역** | 사용할 영역의 폭 `W`, 깊이 `D` | 도달 가능한 경계를 확인하고 작업판에 표시한 뒤 측정. 영역의 모든 점이 가능한지는 자세·경로로 별도 확인 |
| **B 베이스·작업판** | 베이스 기준 작업 영역 중심 위치 `x_c, y_c`, 작업면 높이, 축 정렬각 `ψ`와 작업면 기울기 | 원점·축과 기준점을 표시하고 자·각도계 또는 보정된 좌표 측정 사용. 작업면은 세 개 이상의 비공선 기준점으로 확인 |
| **C 시작 자세** | 6개 관절각 `q_start`, 시작 TCP 위치·방향, 작업면 위 높이 `h_start` | 관절각은 로봇 보고값, TCP는 보정된 기구 모델의 계산값으로 기록하고 외부 기준점·영상으로 대조 |
| **D 그리퍼·도구** | 장착면에서 TCP까지의 3차원 오프셋과 방향, 그리퍼 개구 폭 `w` | 실제 장착 상태에서 치수와 TCP 위치를 보정하고, 도구 축 방향은 별도로 확인 |
| **E 고정 카메라** | 베이스 기준 카메라의 위치 `x, y, z`와 방향, 내부 파라미터·왜곡·해상도 | 보정판으로 내부 보정 후, 베이스 기준 위치를 아는 기준점으로 카메라 자세 추정 |
| **F 손목 카메라** | TCP 기준 카메라의 3차원 위치·방향, 내부 파라미터·왜곡·해상도 | 여러 로봇 자세에서 보정판을 촬영하는 hand–eye 보정과 TCP 장착 변환을 함께 사용 |
| **G 실제 물체** | 선정한 물체의 폭·깊이·높이 또는 지름, 질량, 시작 위치·방향, 받침 높이 | 자·캘리퍼·저울로 실측하고, task별 배치표에 베이스 기준 좌표와 방향 기록 |

작업면이 베이스의 수평면과 평행하다면 `h_start = z_TCP − z_table`로 계산한다. 작업면이 기울어져 있으면 작업면에 수직인 거리를 사용한다. 카메라와 그리퍼의 방향은 yaw·pitch·roll의 축과 적용 순서를 명시하거나 회전행렬·쿼터니언으로 저장한다. 특히 **배치 거리의 축소 비율을 관절각·카메라 각도에 곱하지 않는다.** 카메라 보정은 [OpenCV 내부 보정](https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html)과 [hand–eye 보정 함수](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html)를 참고한다.

### 시뮬레이션 PNG를 활용한 실물 배치

아래 네 장은 **기존 LIBERO 장면을 직접 렌더링한 참고 이미지**다. 앞으로 구성할 custom 환경이나 실물 Mirobot의 검증 결과는 아니다. 같은 장면의 여러 시점에서 작업대·로봇·그리퍼·카메라의 관계를 읽고, 이를 Mirobot 기본 환경 설계에 활용한다. 화면 속 물체는 기존 장면의 구성물이며 실물에는 결정한 task에 필요한 물체를 배치한다.

| 상부 시점 | 정면 시점 |
| --- | --- |
| ![LIBERO 시뮬레이션의 상부 참고 화면](images/libero_reference_top.png) | ![LIBERO 시뮬레이션의 정면 참고 화면](images/libero_reference_front.png) |

| 측면 시점 | 작업 관측 카메라 |
| --- | --- |
| ![LIBERO 시뮬레이션의 측면 참고 화면](images/libero_reference_side.png) | ![LIBERO 시뮬레이션의 작업 관측 참고 화면](images/libero_reference_observation.png) |

| 사진에서 확인할 요소 | Mirobot 실물 환경에 반영하는 방법 |
| --- | --- |
| 상부: 로봇 베이스 뒤쪽, 작업 영역 앞쪽의 관계 | 베이스와 작업 영역 중심을 정하고, 도달 가능한 범위 안에서 앞뒤·좌우 거리를 조정 |
| 정면: 작업면과 초기 그리퍼 사이의 높이 | 실제 작업면을 기준으로 시작 TCP 높이를 정하고, 그리퍼·물체가 지나갈 여유 확보 |
| 측면: 그리퍼 접근 방향과 팔·작업대의 간격 | 같은 접근 방향을 구현할 수 있는 6축 자세를 찾고, 이동 경로의 간섭 확인 |
| 작업 카메라: 작업 영역이 화면에 들어오는 구도 | 영역 모서리에 기준점을 두고 고정 카메라 거리·높이·기울기를 조정한 뒤 보정 |

사진의 픽셀 간격을 실제 길이로 바로 환산하지 않는다. 시뮬레이터의 좌표·카메라 설정과 실물 실측값을 사용해 치수를 정하고, 사진은 최종 배치와 관측 구도를 대조하는 자료로 사용한다.

### 비례식으로 실물 배치를 정하는 방법

Panda와 Mirobot은 링크 길이·관절 수·그리퍼가 다르므로, 한 링크의 길이 비율만으로 전체 배치를 결정하기 어렵다. 여기서는 **두 로봇에서 선택한 사용 가능 작업 영역의 비율**로 평면 배치 초안을 만든다. 관절각과 높이는 Mirobot의 기구 구조와 실제 장착물에 맞춰 별도로 정한다.

먼저 LIBERO custom 환경에서 베이스·작업면·초기 TCP·카메라의 좌표와 방향을 읽는다. 세계 좌표와 로봇 베이스 좌표를 구분하고, TCP는 물체를 잡는 기준점으로 통일한다. [말단 관측 구현](https://github.com/ARISE-Initiative/robosuite/blob/v1.4.0/robosuite/robots/single_arm.py) 실물에서는 그리퍼와 손목 카메라를 장착한 상태로 도달 범위를 확인해 작업 영역을 고른다. 제조사 최대 도달거리만으로 영역을 정하지 않고, 사용할 접근 방향에서 관절 한계와 작업대·카메라 간섭을 확인한다.

LIBERO 쪽 기준 영역도 같은 방식으로 정한다. 사용할 그리퍼 접근 방향과 작업 높이에서 Panda가 이동할 수 있고 카메라로 볼 수 있는 영역을 확인한 뒤, 그 안에서 직사각형을 고른다. 작업면 기준 경계 `x_Pmin, x_Pmax, y_Pmin, y_Pmax`를 저장하면 `W_P = x_Pmax − x_Pmin`, `D_P = y_Pmax − y_Pmin`이고 중심 `c_P`는 경계의 중간점이다. 이 영역은 `table_full_size`가 나타내는 작업대 전체와 구분한다. 실물에서도 같은 조건으로 영역을 선택하므로, 두 로봇의 링크 길이를 억지로 대응시키지 않고 배치 비율을 정할 수 있다.

**① 작업 영역의 폭과 깊이로 배율을 구한다.** 두 작업면의 x축·y축이 같은 방향을 뜻하도록 대응시킨다. LIBERO의 기준 영역을 `W_P × D_P`, 실물의 사용 영역을 `W_M × D_M`이라 하면 다음과 같이 정한다. 네 길이는 같은 단위로 입력한다.

```text
s = min(W_M / W_P, D_M / D_P)
s × W_P ≤ W_M,  s × D_P ≤ D_M
```

하나의 배율을 사용해 앞뒤·좌우 비율을 유지하며, 두 영역의 가로세로 비가 다르면 한쪽에 여유 공간이 남는다. 이 식은 작업 영역의 축을 대응시킨 상태에 적용한다. 배치를 실물 작업면 안에서 추가로 회전시키면 경계를 다시 확인해야 한다.

**② 중심을 기준으로 배치점을 옮긴다.** 각 작업면에 원점과 축을 표시하고, 영역 중심을 각각 `c_P = (c_Px, c_Py)`, `c_M = (c_Mx, c_My)`로 둔다. LIBERO 작업면의 기준점 `(x_P, y_P)`에 대응하는 실물 작업면의 후보 위치는 다음과 같다.

```text
x_M = c_Mx + s × (x_P − c_Px)
y_M = c_My + s × (y_P − c_Py)
```

배율만으로 로봇과 작업 영역 사이의 절대 거리가 정해지지는 않는다. **실물 영역 중심 `c_M`은 Mirobot의 도달 범위를 확인해 먼저 정하고**, 그 중심을 기준으로 초기 TCP의 평면 위치와 필요한 배치 기준점을 계산한다. 이때 물체·그리퍼의 실제 크기가 들어갈 공간과 이동 경로까지 확인한다.

예를 들어 LIBERO 기준 영역이 `400 × 300 mm`, 실물 영역이 `160 × 120 mm`라면 `s = 0.4`다. 두 영역의 원점을 각각 한 모서리에 두어 중심이 `(200, 150)`과 `(80, 60) mm`일 때, LIBERO의 `(250, 125) mm`는 실물 작업면의 **`(100, 50) mm`**에 대응한다. **계산 방법을 보여주는 가정값이며, 현재 Mirobot의 실측 치수나 확정 설치 위치가 아니다.**

**③ 작업면 좌표를 로봇 베이스 좌표로 바꾼다.** 계산한 평면 위치에 실측한 높이를 더해 `p_W = (x_M, y_M, z_M)`를 만든다. 작업면을 `z_M = 0`으로 정하고, 초기 TCP 높이 등은 실제 도구·물체와 이동 여유에서 결정한다. 뒤의 실측 절차로 구한 작업면→베이스 변환을 적용한다.

```text
p_B = R_BW × p_W + t_BW
```

`R_BW`는 작업면 좌표를 베이스 축 방향으로 바꾸는 회전행렬이고, `t_BW`는 작업면 원점의 베이스 기준 위치다. 작업판의 설치 각도와 기울기는 이 변환에 반영한다. 계산한 `p_B`는 배치·시작 자세의 후보이며, 실제 이동 전에는 다음 절차에 따라 역기구학과 경로를 확인한다.

### 계산한 위치를 실제 작업대에 표시하는 방법

제공된 사진의 **오른쪽 베이스와 왼쪽 작업판 배치**를 출발점으로 아래 순서대로 설치 위치를 정한다. 사진의 좌우는 배치를 설명하는 방향이며, 제어 좌표의 축과 부호는 로봇 모델에서 확인한 정의를 사용한다.

| 설치 대상 | 위치를 정하고 표시하는 방법 | 최종 기록 |
| --- | --- | --- |
| **Mirobot 베이스** | 사진 오른쪽 배치에서 고정 상태를 확인하고, 장착 기준점을 작업판에 표시한다. 작업 영역까지 접근이 부족하면 베이스 위치부터 조정하고 좌표 변환을 다시 구한다. | 베이스 장착 기준점·방향, 작업면→베이스 변환 |
| **기본 작업 영역** | 베이스 왼쪽에서 사용 가능한 중심과 폭·깊이를 정한다. 중심에서 좌우 `W_M/2`, 앞뒤 `D_M/2`만큼 표시해 경계를 그리고, 모서리·중앙·이동 경로의 도달 가능성을 확인한다. | 작업 영역 중심의 베이스 좌표, 폭·깊이, 제외 구역 |
| **초기 TCP** | 위 비례식으로 평면 후보 위치를 구하고, 도구와 작업면의 간격을 확인해 높이를 정한다. 그 위치·방향을 구현하는 6축 자세를 찾는다. | 시작 TCP 위치·방향, `q_start`, 복귀 경로 |
| **고정·손목 카메라** | 고정 카메라는 작업 영역 모서리가 화면에 들어오도록 거리·높이·방향을 조정한다. 손목 카메라는 그리퍼와 집는 부분이 보이도록 장착하고, 동작 중 가림까지 확인한다. | 내부 보정값, 베이스 또는 TCP 기준 카메라 위치·방향 |
| **task별 실제 물체** | task를 정한 뒤 확보한 물체를 기본 작업 영역 안에 놓고 시작·목표 위치를 표시한다. 실제 크기와 파지·이동·놓기 경로를 확인한다. | 대상 물체, 시작·목표 좌표, 방향과 허용 배치 범위 |

카메라는 렌즈 시야각과 로봇 형상이 다르므로 거리 배율만으로 구도를 정하지 않는다. 또한 `s`를 실제 물체 크기·관절각·카메라 각도나 정책 출력에 일괄 적용하지 않는다. 배율은 환경 배치의 초안에만 사용하고, 실물 제어에는 Mirobot 실측 좌표와 해당 데이터의 정규화 통계를 사용한다. 최종 설치값은 실측·도달 검증 후 채우며, 지금은 확정하지 않는다.

### Panda의 시작 상태를 Mirobot 시작 자세로 변환

시작 자세는 **작업 영역에 대한 그리퍼의 위치, 접근 방향, 손목 카메라 시야**가 대응하도록 정한다. 팔꿈치 모양이나 Panda의 7개 관절각에 축소 비율을 적용하지 않는다.

| 순서 | 설정 방법 | 확인할 결과 |
| --- | --- | --- |
| ① 기준 맞추기 | Mirobot의 원점 복귀를 수행하고, 베이스 좌표축과 장착한 그리퍼의 TCP 위치·방향 확인 | 위치 단위, 각도 단위·회전 순서, 도구 장착 오프셋 |
| ② 목표 말단 자세 정하기 | 위 배치 비율로 초기 TCP 위치의 후보를 잡고, 그리퍼 접근축과 손가락이 닫히는 방향을 작업대 기준으로 맞춤 | Mirobot의 시작 목표 위치·방향 |
| ③ 6축 관절 자세 구하기 | 목표 TCP 위치·방향을 만드는 관절각을 역기구학으로 계산하거나, TCP를 좌표축 방향으로 조금씩 움직이는 Cartesian 조그로 자세를 찾아 관절값을 기록 | 시작 관절값 `q_start = [J1, …, J6]` |
| ④ 자세와 복귀 경로 확인 | 관절 한계·특이 자세·테이블 충돌·카메라 가림을 확인하고, 시작점으로 돌아오는 경유점과 경로 검사 | 실행 가능한 시작 자세와 복귀 경로 |
| ⑤ 반복 복귀 검증 | 같은 경로로 여러 번 복귀해 TCP 위치·방향, 그리퍼 상태와 두 카메라 화면 비교 | 시작 상태 오차와 반복성 기록 |

두 로봇의 도구 좌표축이 다르면 장착 오프셋을 반영해 그리퍼 방향을 맞춘다. 역기구학 해가 없거나 관절 한계에 가까우면 시작 위치·높이·접근 방향을 조정하고 다시 확인한다. 여러 해가 있으면 관절 한계에서 여유가 있고 복귀 경로가 짧은 자세를 선택한다. 기구 모델과 제어 연결은 [WLKATA의 Mirobot URDF·MoveIt 코드](https://github.com/wlkata/Wlkata_Mirobot_Ros2)를 참고하되, 실제 장착 장치와 기구 치수가 일치하는지 확인한다.

**원점 복귀는 기계의 기준을 잡는 과정이고, `q_start` 복귀는 실험을 시작하는 과정**이다. 필요한 원점 복귀 후 최신 상태 응답으로 완료를 확인하고, 매 에피소드에서는 검증한 경로로 `q_start`에 복귀해 도달 여부와 그리퍼 초기 상태를 확인한다. SDK 함수가 반환됐다는 사실만으로 이동 완료를 판단하지 않는다. [WLKATA 제어 SDK](https://github.com/wlkata/WLKATA-Python-SDK-wlkatapython)

최종 설정에는 `q_start`, 시작 TCP 위치·방향, 그리퍼 초기 상태, 좌표 변환·카메라 보정값, 복귀 경로를 함께 저장한다. 허용 오차는 그리퍼와 물체의 여유 간격을 기준으로 정하며, 로봇 보고 상태와 외부 기준점·영상의 반복 측정을 비교해 확인한다. 실제 치수와 관절각은 실측 후 확정한다. 매회 초기 상태는 이 공통 설정과 해당 회차의 물체 배치를 합쳐 기록한다.

### D405 실측 준비

실측에는 **Intel RealSense D405 두 대의 RGB·깊이 영상**을 사용한다. D405의 내장 깊이 센서와 D4 프로세서가 거리 정보를 제공하고, RealSense SDK가 이를 읽는다. OpenCV는 RGB 화면에서 기준점과 측정점을 클릭하는 데 사용한다. [D405 사양](https://www.realsenseai.com/product-family/d405-series/)

1. **기준점을 작업종이에 표시한다.** 앞에서 정한 종이 모서리 원점 `O`, 긴 변 방향 `+x`, 짧은 변 방향 `+y`를 유지하고 종이 표면을 `Z=0`으로 둔다. 두 카메라에 모두 보이는 곳에 아래처럼 작은 직사각형 A·B·C·D를 표시한다. 자로 **표식 중심 사이**를 재어 `AB=CD=W`, `AD=BC=D`인지 확인한다. 각도기로 직각을 확인하고 두 대각선도 `√(W²+D²)`와 대조한다. 자는 표면에 밀착시키고 눈금 정면에서 읽으며, 다시 대어 5회 잰 값의 평균과 범위를 기록한다.

```text
D ───────────── C             +y ↑
  │       E       │          +Z: 종이 위쪽
A ───────────── B             +x →
```

   `O`에서 A까지 x·y 방향 거리 `(a_x,a_y)`도 재서 기록한다. A가 O라면 두 값은 0이다. E는 눈대중으로 놓지 않고 A에서 x방향 `W/2`, y방향 `D/2`를 재어 표시하며, 보정에 넣지 않고 검증에 사용한다. 200×150 mm는 기준 사각형의 예시일 뿐이고 실행 명령에는 실제로 잰 값만 넣는다.

2. **카메라와 초기 자세를 고정한다.** 고정 카메라에서 A~E가 모두 보이게 한다. 손목 카메라는 사용할 Mirobot 시작 자세에 정지시킨 뒤 같은 기준점을 촬영한다. 카메라를 일련번호로 구분해 각각 측정한다. 손목·카메라·작업종이가 움직이면 `R→C`로 새 영상에서 보정한다.
3. **검증할 높이도 준비한다.** 자로 높이를 잰 평평한 물체를 하나 준비한다. E로 평면 좌표를 검증하고, 이 물체의 윗면으로 높이값을 따로 검증한다. 깊이 측정 대상이 D405의 권장 거리 7~50 cm 안에 보이는지 확인한다. 측정값은 검증 전까지 **‘실측 필요’**로 관리한다.

### 실제 카메라 설치와 배치

LIBERO의 고정 시점 `agentview`와 손목 시점 `robot0_eye_in_hand`에 대응하도록 D405 두 대를 배치한다. 외부 카메라는 작업종이 왼쪽의 책상 가장자리에 클램프·지지봉·볼헤드로 고정해 작업 영역을 내려다보게 한다. 두께 2.5 cm인 상판에 클램프가 밀착하는지 확인하고, 지지봉은 짧게 사용해 흔들림을 줄인다. 손목 카메라는 그리퍼와 집는 위치가 보이도록 고정한다.

원본 `agentview`의 위치는 `(0.658613, 0, 1.610350) m`, 작업면 높이는 `0.90 m`다. 작업면 기준점을 `(0, 0, 0.90) m`로 두고 공칭 reach 비율을 적용하면 다음 설치 후보를 얻는다.

```text
배율 후보 = Mirobot 315 mm / Panda 855 mm ≈ 0.3684
렌즈 높이 = (1.610350 − 0.90) × 100 × 0.3684 ≈ 26.2 cm
기준점까지 수평 거리 = 0.658613 × 100 × 0.3684 ≈ 24.3 cm
```

원본 광축의 하향각은 **38.9°**이고, 위 위치에서 기준점을 영상 중앙에 맞추는 각도는 `atan2(26.2, 24.3) ≈ 47.2°`다. 두 조건은 조준 방향이 다르므로 시야를 확인해 선택한다. 로봇마다 reach의 말단 기준과 실제 도달 영역이 다르므로 최종 배치는 앞의 작업 영역 비례식과 보정으로 확정한다. **렌즈 높이·수평 거리·하향각은 실측 필요**다.

체결부를 잠근 뒤 작업 영역의 모서리와 물체 이동 경로가 보이는지 확인하고, 손목 영상에서 그리퍼가 물체를 가리지 않도록 방향을 조절한다. 외부 USB 케이블은 지지대에 고정하고 손목 케이블에는 움직일 여유를 둔다. Homing 높이 기록은 **30 cm**이며, 실험 시작 TCP 높이는 앞의 시작 자세 절차로 정한다. 로봇 가동부와 외부 카메라·지지대 사이에는 **7 cm를 초기 여유 목표**로 두고 전체 경로의 최소 3차원 이격을 확인한다(**실측 필요**). D405 깊이를 사용할 때는 물체가 권장 거리 **7~50 cm**에 있는지 따로 확인한다.

근거: [LIBERO 카메라 설정](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/problems/libero_tabletop_manipulation.py) · [Mirobot 사양](https://www.wlkata.com/pages/product-mirobot-robotic-arm) · [Panda 매뉴얼](https://download.franka.de/documents/100010_Product%20Manual%20Franka%20Emika%20Robot_10.21_EN.pdf) · [MuJoCo 카메라 방향 규약](https://mujoco.readthedocs.io/en/3.3.2/XMLreference.html#body-camera) · [D405 사양](https://www.realsenseai.com/product-family/d405-series/)

### D405 측정 실행과 결과 확인

#### 프로그램 실행

ZIP을 풀고 MD가 있는 폴더에서 터미널을 연다. **Windows 64비트 Python 3.11**을 기준으로 다음을 실행한다. Python이 없다면 `winget install --exact --id Python.Python.3.11`로 설치하고 터미널을 다시 연다. 측정 프로그램은 [scripts/measure_d405.py](scripts/measure_d405.py)에 포함했다. D405 두 대를 이 PC의 USB 포트에 연결하고 카메라를 사용하는 다른 프로그램은 닫는다.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install numpy opencv-python pyrealsense2
.\.venv\Scripts\python.exe .\scripts\measure_d405.py --list
```

`Camera serials`에 나온 번호를 본체의 일련번호와 대조해 고정·손목 카메라를 구분한다. 목록이 `[]`이면 USB 연결부터 확인한다. 아래 명령의 `카메라일련번호`, `200`, `150`, `20`, `0 0`을 각각 선택한 번호, 실측한 `W`, `D`, 검증용 물체 높이, A의 종이 좌표 `a_x a_y`(모두 mm)로 바꾼다. 먼저 고정 카메라를 측정하고 `Q`로 종료한 뒤, 일련번호만 바꿔 손목 카메라에서 같은 순서를 수행한다. **로봇 베이스 좌표도 필요하면 아래 ‘종이 좌표를 Mirobot 베이스 좌표에 연결’을 먼저 진행한다.**

```powershell
.\.venv\Scripts\python.exe .\scripts\measure_d405.py --serial 카메라일련번호 --width-mm 200 --depth-mm 150 --height-check-mm 20 --origin-mm 0 0
```

| 순서 | 화면에서 할 일 | 터미널에서 확인할 값 |
| --- | --- | --- |
| **① C: 기준 맞추기** | `C`를 누르고 멈춘 화면에서 **A→B→C→D** 순서로 클릭 | `camera_position_mm`: 종이 기준 카메라 위치. `camera_height_mm`: 종이 위 높이. `camera_down_deg`: 광축 하향각. `calibration_fit_rmse_mm`: 네 기준점을 맞춘 잔차 |
| **② V: 평면 검증** | `V`를 누르고 **E** 클릭 | `check_point_mm`: 종이 좌표. `position_error_mm`: E의 기준 위치 `(a_x+W/2,a_y+D/2,0)`와의 차이 |
| **③ H: 높이 검증** | 검증용 물체를 놓고 `R`로 새 영상을 받은 뒤 `H`를 누르고 평평한 윗면 클릭 | `height_mm`: 측정 높이. `height_error_mm`: 자로 잰 높이와의 차이 |
| **④ M: 실제 측정** | `R`로 새 영상을 받은 뒤 `M`을 누르고 **P1→P2→P3** 클릭 | P1–P2 길이, 수평 거리, 방향각, P2를 꼭짓점으로 한 세 점의 각도와 각 점의 XYZ |
| **⑤ 저장·종료** | 같은 카메라의 측정을 마치면 `Q` | 결과 JSON, RGB PNG, 원본 깊이·스케일·내부 파라미터 NPZ가 자동 저장됨 |

표식 중앙이나 같은 표면의 안쪽을 클릭한다. 클릭점 깊이가 0이거나 주변 3×3 픽셀의 깊이 차이가 5 mm를 넘으면 프로그램이 재선택을 요구한다. 이때 `R`을 누르고 다시 해당 키를 눌러 점을 고른다. 5 mm는 경계 혼합을 걸러내는 설정값이며 측정 정확도를 뜻하지 않는다. 유효한 점은 주변 깊이 중앙값을 사용한다. **RGB를 원본 깊이 영상에 맞춰 표시하고 원본 깊이 프레임의 내부 파라미터로 계산**하므로 픽셀과 깊이 좌표가 대응한다.

#### 출력값을 배치와 시작 자세에 쓰는 방법

- **영역 폭·배치 거리:** `length_mm`는 P1–P2의 3차원 거리, `horizontal_mm`는 종이 위 수평 거리다. 종이 위 경계점으로 폭·깊이를 재고, 마주 보는 두 모서리의 `midpoint_P1P2_mm`으로 영역 중심을 구한다. 길이만 재더라도 P3는 같은 표면의 다른 점을 클릭한다.
- **높이:** `points_mm`의 각 행은 선택한 점의 `(X,Y,Z)`다. `Z`가 작업종이 위 높이다. 그리퍼 끝 두 점의 중간점을 실험 TCP로 정의했다면 `midpoint_P1P2_mm`을 사용한다. 기존 TCP가 다른 지점이면 그 정의와 장착 오프셋을 먼저 맞춘다.
- **각도:** `line_yaw_deg`는 P1→P2의 종이 x축 기준 방향각, `angle_at_P2_deg`는 P2를 꼭짓점으로 한 3차원 각도다. 초기 그리퍼의 기준선이나 물체 방향을 정해 측정하며, 로봇의 J1~J6 관절각은 SDK 보고값으로 별도 기록한다. 수직선처럼 수평 방향이 없는 경우 `line_yaw_deg`는 `null`이다.
- **두 시점 대조:** 두 카메라에서 같은 기준점의 XYZ를 측정해 비교한다. 각 카메라를 A~D로 같은 종이 좌표에 맞춘 결과를 사용한다.

다음은 동봉 코드의 핵심이다. `R, t`는 A~D의 깊이 좌표와 실측한 종이 좌표를 맞춰 구한 변환이며, `t`의 단위는 mm다. 전체 프로그램은 프레임 취득·RGB 정렬·클릭·검증·저장까지 수행한다.

```python
# RGB를 원본 깊이 픽셀에 맞춘 뒤 깊이 프레임의 내부 파라미터 사용
align = rs.align(rs.stream.depth)
frames = align.process(pipe.wait_for_frames())
depth_frame = frames.get_depth_frame()
intr = depth_frame.profile.as_video_stream_profile().intrinsics

# 유효점 검사를 통과한 3×3 깊이의 중앙값(m)
depth = np.asanyarray(depth_frame.get_data())
patch = depth[max(0, v-1):v+2, max(0, u-1):u+2]
z_m = float(np.median(patch[patch > 0])) * scale
# 카메라 XYZ(m) → 작업종이 XYZ(mm)
p_c_mm = np.asarray(rs.rs2_deproject_pixel_to_point(intr, [u, v], z_m)) * 1000
p_w_mm = R @ p_c_mm + t

# 세 점의 길이와 각도. P2가 각도의 꼭짓점이다.
a, b = p1 - p2, p3 - p2
length_mm = np.linalg.norm(p2 - p1)
angle_deg = np.degrees(np.arccos(np.clip(
    a @ b / (np.linalg.norm(a) * np.linalg.norm(b)), -1, 1)))
```

깊이는 카메라 광축 방향 값이므로 **깊이 숫자 자체를 물체 높이로 사용하지 않고**, 위처럼 작업종이 좌표로 바꾼다. 카메라 위치는 SDK의 깊이 광학 원점 기준이며 카메라 케이스나 지지대 높이와 구분한다.

#### 반복 측정과 시작 자세 확인

같은 P1~P3를 **새 프레임에서 5회** 측정하고 `Q`로 종료한 뒤 다음을 실행한다. `카메라일련번호`는 앞에서 사용한 번호로 바꾼다. 마지막 측정 다섯 개의 길이·각도·XYZ에 대해 평균(`mean`), 표준편차(`std`), 최솟값(`min`), 최댓값(`max`)을 출력한다.

```powershell
.\.venv\Scripts\python.exe .\scripts\measure_d405.py --summary .\d405_카메라일련번호_results.json
```

`calibration_fit_rmse_mm`는 보정에 쓴 네 점의 잔차다. 실제 정확도는 별도 E와 높이 검증값으로 확인한다. task의 파지·놓기 여유를 기준으로 정한 허용 오차를 넘으면 표식, 클릭 위치, 흔들림을 바로잡고 `R→C→V→H`를 다시 수행한다. 반사 때문에 깊이가 비거나 두 시점의 값이 맞지 않는 점은 측정 완료로 처리하지 않는다. 같은 자의 영점·눈금 오차는 반복이나 D405 보정만으로 없어지지 않으므로, 더 작은 오차가 필요하면 별도 길이 기준이나 교정된 도구로 검증한다.

시작 자세의 반복성은 **고정 카메라를 유지한 채** Mirobot을 같은 `q_start`로 5회 복귀시키고, 매번 같은 그리퍼 표식 세 점의 XYZ와 방향각을 재어 비교한다. 이것은 복귀 편차이며 로봇의 절대 위치 정확도와 구분한다. SDK 관절값도 함께 기록한다. 검증 전 배치값은 계속 **‘실측 필요’**로 둔다.

#### 종이 좌표를 Mirobot 베이스 좌표에 연결

위 값만으로 종이 위 설치 위치를 표시할 수 있다. 로봇 명령에 사용할 `p_B`가 필요하면 다음 등록을 추가한다.

1. **로봇이 보고하는 TCP와 실제 팁을 맞춘다.** 컨트롤러의 TCP 정의와 장착 도구 오프셋을 확인하고 보정된 기준 팁으로 A~D 중심에 차례로 접근한다. 각 점에서 정지한 뒤 **명령값이 아닌 현재 TCP의 베이스 XYZ(mm)**를 기록한다. 현재 제어 프로그램의 상태 조회 `?` 응답에서 `Cartesian coordinate(XYZ RxRyRz)`의 앞 세 값을 읽고, `Angle`의 관절값도 저장한다. 실제 응답의 필드·축·단위와 TCP 기준은 먼저 확인한다. 그리퍼 끝이 보고 TCP와 다르면 오프셋을 반영해야 하며, 기존 `inverse.py`의 누적 명령 변수를 측정값으로 대신 쓰지 않는다.
2. MD 폴더에 `base_points_mm.json`을 만들고 아래 `null`을 A~D의 **실제 보고 좌표 세 숫자**로 각각 바꾼다. `null` 상태에서는 등록할 수 없다.

```json
{"A": [null, null, null], "B": [null, null, null],
 "C": [null, null, null], "D": [null, null, null]}
```

3. 아래 `W`, `D`, A의 좌표를 실측값으로 바꿔 실행한다. `work_to_base.json`에 `R_BW`, `t_BW_mm`과 대응점 잔차가 저장된다. 이후 카메라 실행 명령 끝에 `--base-transform .\work_to_base.json`을 붙이면 `points_base_mm`도 출력한다.

```powershell
.\.venv\Scripts\python.exe .\scripts\measure_d405.py --register-base .\base_points_mm.json --width-mm 200 --depth-mm 150 --origin-mm 0 0
```

등록에 쓰지 않은 E에서도 팁의 로봇 보고 위치와 변환한 D405 위치를 대조한다. 이 결과에는 TCP·로봇 기구 모델 오차가 포함된다. 베이스·종이를 옮기면 등록을 다시 한다. 손목 카메라의 위 보정은 고정된 시작 자세에서 배치를 재기 위한 것이며, 로봇 이동 중의 카메라–TCP 변환은 앞 표의 여러 자세 hand–eye 보정 항목으로 남긴다.

[RealSense 깊이·좌표 변환](https://dev.realsenseai.com/docs/projection-in-realsense-sdk-2-0/) · [공식 RGB–깊이 정렬 예제](https://github.com/realsenseai/librealsense/blob/master/wrappers/python/examples/align-depth2color.py)

#### 아직 실측이 필요한 값

기존 상판·작업종이 치수와 Homing 높이·동작 범위 기록은 유지한다. 아래 값은 측정·검증이 끝나면 결과와 날짜를 채운다.

| 기록할 값 | 현재 상태 | 이번 절차에서 확인할 방법 |
| --- | --- | --- |
| 고정 카메라 위치·높이·하향각 | **실측 필요** | `C` 결과의 위치·높이·각도. 26.2 cm·24.3 cm는 설치 후보 |
| 사용 영역 경계·중심 `W_M,D_M,c_M` | **실측 필요** | 실제 도달·경로를 확인한 경계점의 `M` 좌표와 거리 |
| 작업면→베이스 변환과 축 정렬 | **실측 필요** | A~D의 TCP 보고 좌표로 등록하고 E에서 대조 |
| 시작 TCP 위치·방향과 `q_start` | **실측 필요** | 같은 그리퍼 표식의 `M` 결과와 TCP·관절 보고값. Homing 높이와 구분 |
| 그리퍼 개구 폭·장착면→TCP 오프셋 | **실측 필요** | 보이는 기준점 간 `M` 거리와 장착 도구 치수·TCP 정의 대조. 가린 지점은 자로 별도 측정 |
| 손목 카메라–TCP 위치·방향 | **실측 필요** | 초기 정지 자세의 `C` 결과를 먼저 기록. 이동 중 변환은 여러 자세의 hand–eye 보정 필요 |
| 카메라 내부 파라미터·왜곡 | **실측·확인 필요** | SDK가 제공한 값을 NPZ에 저장하고 E·높이 검증으로 해당 설치에서의 오차 확인 |
| 경로 중 최소 이격·케이블 여유 | **실측 필요** | 각 정지 자세에서 보이는 두 표면의 `M` 거리와 실제 경로 대조. 가림 구간은 별도 확인 |
| 물체 치수·높이·질량·시작·목표 배치 | **실측 필요** | 치수·높이·좌표는 `M`, 질량은 저울로 별도 측정 |
| 좌표·방향 오차와 시작 자세 복귀 편차 | **실측 필요** | E·높이 검증값과 동일 조건 5회 측정 결과 |

### 실물 task와 물체 배치

기본 환경이 마련되면 확보할 수 있는 물체의 크기·무게·집는 부분을 확인하고 Mirobot으로 조작 가능한 task를 정한다. 예를 들어 작은 물체와 받침을 사용할 수 있다면 “시작 영역의 물체를 집어 받침 위에 놓기”로 정의할 수 있다. 최종 task는 실제 물체와 작업 가능 범위를 확인한 뒤 확정한다.

task 명세에는 **작업 지시, 대상 물체, 시작·목표 영역, 허용하는 초기 배치 범위, 성공 조건, 제한 시간**을 기록한다. 작업대·로봇·카메라는 유지한 채 물체를 배치하고, 사람이 Mirobot을 조작해 집기부터 놓기까지 경로와 카메라 가림을 확인한다. 이 확인을 마친 배치에서 시연 수집을 시작한다.

### Task별 BDDL 작성과 실물 배치 반영

같은 기본 작업대에서 task를 바꿀 때는 **물체 목록, 시작 영역, 초기 조건, 목표 조건, 언어 지시문을 task별 `.bddl` 파일로 저장하고 그 파일로 환경을 새로 생성한다.** 로봇과 카메라를 매번 새로 만드는 방식은 아니다. BDDL의 `(problem LIBERO_Tabletop_Manipulation)`은 환경 클래스 이름이며, 개별 task는 파일명과 `:language`로 구분한다. 로봇의 관절 각도·링크 길이·카메라 위치는 BDDL 밖의 로봇 모델과 환경 설정에 둔다.

작성 순서는 다음과 같다.

1. **실물 task를 먼저 정한다.** 옮길 물체, 출발 위치, 도착 영역, 성공 조건을 기록한다. D405로 측정한 좌표를 시뮬레이션 작업대 좌표로 바꿔 BDDL 영역에 넣는다. Mirobot 크기로 만든 장면에서 작업대 x·y 원점을 실물 사용 영역 중심 `c_M`에 맞추고 축 방향도 같게 두었다면, `x_table=(x_paper−c_Mx)/1000`, `y_table=(y_paper−c_My)/1000`으로 **mm를 m로** 바꾼다. 작업대 축·원점이 다르면 그 회전·이동 변환을 먼저 적용한다. Panda 장면으로 배치 초안을 만드는 단계에서는 앞의 배율·중심 대응식을 사용한다.
2. **task마다 별도 파일을 만든다.** `:objects`에는 사용할 등록 asset, `:regions`에는 출발·도착 범위, `:init`에는 시작 관계, `:goal`에는 성공 관계, `:language`에는 지시문을 적는다. 출발 영역의 폭은 물체 크기와 허용할 초기 위치 변동을 고려해 정하고, 목표 영역은 실물의 성공 판정 영역과 대응시킨다.
3. **수정한 파일로 환경을 다시 생성한다.** 이미 생성된 환경에서 파일만 편집해도 장면은 바뀌지 않는다. `OffScreenRenderEnv(bddl_file_name=...)`에 새 경로를 전달한 뒤 `reset()`으로 초기 장면을 확인한다.

아래는 공식 `tabletop_task_suites_generator()`를 사용해 기존 검은 그릇 asset의 이동 task를 생성하는 **작성 예시**다. 숫자는 실측값이 아니며, 이 task의 물리 실행과 성공 조건은 아직 검증하지 않았다. 실제 물체가 확정되면 등록 asset 이름, 영역, 지시문, 목표 조건을 함께 바꾼다. 코드는 LIBERO와 해당 버전의 의존성이 설치된 Python 환경에서 실행한다.

```python
from pathlib import Path
from libero.libero.utils.bddl_generation_utils import (
    tabletop_task_suites_generator, get_result,
)

folder = Path("custom_tasks")
folder.mkdir(exist_ok=True)
task_file = folder / "move_bowl_to_target.bddl"
regions = [
    dict(region_name="start", target="main_table",
         ranges=[(-0.12, -0.02, -0.08, 0.02)]),
    dict(region_name="target", target="main_table",
         ranges=[(0.05, -0.05, 0.15, 0.05)], rgba=[0, 1, 0, 0.3]),
]
definition = tabletop_task_suites_generator(
    language="move the black bowl to the marked target region",
    xy_region_kwargs_list=regions,
    affordance_region_kwargs_list=[],
    fixture_object_dict={"table": ["main_table"]},
    movable_object_dict={"akita_black_bowl": ["akita_black_bowl_1"]},
    objects_of_interest=["akita_black_bowl_1"],
    init_states=[("On", "akita_black_bowl_1", "main_table_start")],
    goal_states=[("And", ("On", "akita_black_bowl_1", "main_table_target"))],
)
task_file.write_text(get_result(definition), encoding="utf-8")
```

`tabletop_task_suites_generator()`가 위 입력을 BDDL 문법으로 조립하고, `get_result()`가 파일에 쓸 문자열로 변환한다. 목표만 바뀌면 `goal_states`와 지시문을, 시작 배치가 바뀌면 `regions`와 `init_states`도 바꿔 새 파일을 만든다. `On`은 물체가 지정 영역 위에 놓였는지를 LIBERO의 판정 함수로 확인하는 관계다. 실물에서도 같은 목표 영역과 놓임 조건을 기록해야 한다. [공식 BDDL 생성 함수](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/utils/bddl_generation_utils.py) · [목표 판정 함수](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/predicates/base_predicates.py)

생성한 파일은 다음처럼 직접 불러온다. `task_file`은 위 코드에서 만든 경로다. 이 예시의 로봇은 기존 Panda이며, Mirobot 모델 연결은 2절의 등록 절차를 따른다.

```python
import numpy as np
from libero.libero.envs import OffScreenRenderEnv

env = OffScreenRenderEnv(
    bddl_file_name=str(task_file.resolve()),
    robots=["Panda"],
    camera_names=["agentview", "robot0_eye_in_hand"],
    camera_heights=256, camera_widths=256,
)
try:
    env.seed(0)
    obs = env.reset()
    print("지시문:", env.language_instruction)
    print("초기 목표 달성:", env.check_success())
    # 관측 영상·배치·충돌·로봇 시작 자세를 확인한 상태만 보관한다.
    np.save(folder / "move_bowl_to_target.init.npy", env.get_sim_state())
    obs = env.set_init_state(np.load(folder / "move_bowl_to_target.init.npy"))
finally:
    env.close()
```

초기 관측에서 물체 종류·시작 위치·목표 영역을 확인하고, 목표가 처음부터 성립하지 않는지도 확인한다. `check_success()`가 `False`라는 것만으로 목표를 달성할 수 있다고 판단하지 않으며, 실제로 물체를 목표 조건에 놓았을 때 `True`가 되는 것까지 확인한다. 저장한 `.init.npy`는 **해당 환경의 전체 MuJoCo 상태**이며, 기본 benchmark의 `.pruned_init` 파일과는 구분한다. 목표·지시문만 바꾸고 로봇·물체 모델·초기 배치가 같을 때는 같은 상태를 재사용할 수 있지만, 물체 추가·삭제, 로봇 교체, XML 구조 또는 초기 배치 변경 시에는 새 환경에서 다시 저장한다. `seed(0)`만으로 다른 구조의 환경 사이에 같은 상태가 보장되지는 않는다. [환경 생성·상태 저장과 복원](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/env_wrapper.py)

#### BDDL의 배치를 실제 Mirobot 환경에 옮기기

실물에서는 BDDL을 모터 명령으로 실행하지 않고 **같은 task의 물체·출발·목표 조건을 재현**한다. 아래 순서로 시뮬레이션과 실물의 배치표를 맞춘다.

| 순서 | 실물에서 할 일 | 시뮬레이션에 반영할 항목 |
| --- | --- | --- |
| **① 물체 대응** | 확보한 물체의 크기·집는 부분을 재고 asset과 대조 | 다르면 XML·mesh·충돌 형상·질량 등을 맞춤. `:regions`만 바꿔서는 물체 형상이 바뀌지 않음 |
| **② 출발·목표 표시** | 종이에 실측한 시작 중심과 허용 영역, 목표 영역 경계를 표시 | 앞의 좌표 변환으로 영역 경계를 m 단위로 바꿔 `ranges=(x_min,y_min,x_max,y_max)`에 입력 |
| **③ 시작 상태 재현** | 같은 `q_start`로 복귀하고 그리퍼 상태를 맞춘 뒤, D405의 `M`으로 물체·그리퍼 표식을 확인 | 6축 `init_qpos`와 새 초기 상태 저장. 관절각과 카메라 위치는 BDDL 밖에 설정 |
| **④ 조건 대조** | 목표 영역에 실제 물체를 놓고 위치·놓임 조건을 확인. 사람이 전체 경로를 수행해 도달·가림을 확인 | 같은 상태에서 `check_success()`를 확인. 성공 위치·자세와 판정 허용 오차를 task 명세에 기록 |

일반 이동 물체의 초기 회전은 확인한 코드에서 region의 `:yaw_rotation`이 아니라 **물체 모델의 `rotation`·`rotation_axis`**를 사용한다. 실측 방향은 해당 모델 설정 또는 배치 sampler에 반영해야 한다. 최종 실물 배치에는 축소 비율로 얻은 초안 대신 검증한 실측 좌표를 사용한다. [물체 로딩과 초기 배치 처리](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/bddl_base_domain.py)

파일을 직접 불러올 때는 benchmark 등록이 필요 없다. 공식 suite 평가 루프에 넣을 때만 BDDL 경로·지시문·초기 상태를 제공하는 custom benchmark를 연결한다. 생성기용 `register_task_info()`와 평가용 benchmark 등록은 별개다. [task 생성 등록](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/utils/task_generation_utils.py) · [평가 task 등록](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/benchmark/__init__.py)

## 4. Mirobot 시연 수집과 end-to-end 학습

### 영상과 로봇 동작을 함께 기록하는 시연

사람이 조작 인터페이스로 Mirobot을 움직여 task를 수행한다. 고정·손목 카메라 영상, 로봇이 보고한 상태, 그 시점 이후에 보낸 제어 명령을 같은 시간축에 기록한다.

| 기록 항목 | 필요한 내용 |
| --- | --- |
| 두 카메라 영상 | 촬영 시각, 원본 영상, 카메라 설정 |
| 로봇 상태 | 말단 위치·자세, 그리퍼 상태와 상태 취득 시각 |
| 동작 명령 | 실행할 위치·회전 변화량, 그리퍼 명령, 전송·완료 시각 |
| 작업·에피소드 정보 | 작업 지시, 초기 배치, 성공 여부, 중단 이유 |

**영상만 촬영하면 선택한 정책을 학습할 동작 정답이 확보되지 않는다.** 관측 직후 사람이 로봇에 보낸 명령을 함께 저장해야 영상 속 상황과 다음 동작을 연결할 수 있다. 목표 명령과 로봇 보고값·기구 모델로 추정한 도달 상태를 구분하고, 말단 자세를 순기구학으로 계산할 때는 로봇이 보고한 관절값을 사용한다.

**한 step은 기록과 제어의 한 단위이고, 동작 청크는 여러 step의 명령을 묶은 것이다.** 시연 전에 사전 구동 시험으로 한 step을 고정 시간 간격으로 할지, 명령 완료 단위로 할지 정한다. 절대 목표 자세로 조작한다면 해당 관측의 말단 자세를 기준으로 위치·회전 변화량을 계산해 기록한다. 긴 이동을 나누는 규칙과 한 청크의 16단계가 뜻하는 시간·실행 단위를 수집·학습·추론에서 동일하게 유지한다.

여러 시작 위치와 물체 방향에서 시연을 모으고 성공 조건과 영상·상태·동작의 시간 정렬을 검수한다. 행동 모방 학습에는 검수를 통과한 성공 시연을 사용한다. 실패·중단 기록은 원인 분석용으로 구분해 보관하며, 성공 시연을 전제하는 공식 데이터 로더 경로에 섞지 않는다. 학습·검증 데이터는 에피소드 단위로 나누고, 최종 평가용 초기 배치는 별도로 둔다. [공식 데이터 로더](https://github.com/NVlabs/cosmos-policy/blob/18a2accadf4e7a3531e56754102af5a24d2316da/cosmos_policy/datasets/libero_dataset.py)

### 관측에서 동작을 예측하는 정책 학습

이 연구에서 end-to-end는 **카메라 영상·로봇 상태·작업 지시를 입력받아 다음 동작 청크를 직접 예측하는 방식**을 뜻한다. 사람이 수행한 시연을 정답으로 삼아 관측과 동작의 대응 관계를 학습한다. Cosmos Policy의 로봇 시연 기반 학습 구조를 사용하며, 영상·상태 전처리와 실물 제어 변환은 별도로 구현한다. [Cosmos Policy 논문](https://arxiv.org/abs/2601.16163)

```text
고정·손목 영상 + 로봇 상태 + 작업 지시
                  ↓
             Cosmos Policy
                  ↓
       말단 위치·회전 변화량 + 그리퍼 명령
```

기본 입력 상태는 그리퍼 2값·말단 위치 3값·쿼터니언 4값의 9차원이며, 출력은 단계마다 말단 위치·회전 6값과 그리퍼 1값으로 이루어진 16단계 동작 청크다. Mirobot의 그리퍼 관측을 어떻게 표현할지 정하고, 좌표계·단위·주기와 쿼터니언 순서(`xyzw`)를 수집·학습·추론에서 일치시킨다. 차원만 맞추는 임의 값 채우기로 호환성을 판단하지 않는다. [모델 카드](https://huggingface.co/nvidia/Cosmos-Policy-LIBERO-Predict2-2B) · [관측 코드](https://github.com/NVlabs/cosmos-policy/blob/18a2accadf4e7a3531e56754102af5a24d2316da/cosmos_policy/experiments/robot/libero/run_libero_eval.py)

추가 학습에는 다음 설정이 필요하다.

- **데이터 변환:** 실물 영상·상태·동작과 필요한 미래 관측·성공 정보를 공식 데이터 로더 형식에 맞춘다. 시뮬레이터 상태 재생 대신 Mirobot 기록을 읽는 변환기를 작성한다.
- **초기 가중치:** `checkpoint.load_path`를 내려받은 `Cosmos-Policy-LIBERO-Predict2-2B.pt`로 지정한다. 공식 LIBERO 학습 설정의 기본 시작점은 Video2World이므로 이 항목을 변경한다.
- **언어·정규화:** task 문장을 T5 언어 모델로 변환한 숫자 표현인 텍스트 임베딩을 준비하고, Mirobot 학습 데이터에서 상태·동작 통계를 산출한다. 추론에도 같은 전처리와 통계를 사용한다.

[공식 데이터 로더](https://github.com/NVlabs/cosmos-policy/blob/18a2accadf4e7a3531e56754102af5a24d2316da/cosmos_policy/datasets/libero_dataset.py)와 [학습 설정 코드](https://github.com/NVlabs/cosmos-policy/blob/18a2accadf4e7a3531e56754102af5a24d2316da/cosmos_policy/config/experiment/cosmos_policy_experiment_configs.py)를 기준으로 연결하되, Mirobot 데이터 기록기·변환기·제어 연결은 이번 연구에서 구현할 부분이다. PML GPU 4~7의 가용 메모리를 확인하고 작은 배치로 데이터와 손실 계산이 정상인지 검증한 뒤 본 학습을 진행한다.

## 5. 결론

| 구분 | 최종 사용 대상 | 코드·모델 |
| --- | --- | --- |
| 기본 환경의 기준 | **Cosmos Policy-LIBERO와 연결되는 LIBERO tabletop 기반 custom 환경** | [LIBERO tabletop](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/problems/libero_tabletop_manipulation.py) · [Cosmos 환경 생성](https://github.com/NVlabs/cosmos-policy/blob/18a2accadf4e7a3531e56754102af5a24d2316da/cosmos_policy/experiments/robot/libero/libero_utils.py) |
| 추가 학습의 출발 모델 | **`nvidia/Cosmos-Policy-LIBERO-Predict2-2B`** | [Hugging Face 모델](https://huggingface.co/nvidia/Cosmos-Policy-LIBERO-Predict2-2B) · [Cosmos Policy 코드](https://github.com/NVlabs/cosmos-policy) |
| 실물 추론 모델 | 위 모델을 Mirobot 시연으로 추가 학습한 체크포인트 | 실물 시연 수집·학습 후 생성 |

탁상 단일 팔 구성, 초기 조건의 재현, 공개된 정책 관측 연결을 함께 고려해 **기본 환경으로 LIBERO를 선택한다.** 작업대·카메라·시작 상태는 LIBERO 원본 코드에서 설정하고, 관측은 Cosmos Policy-LIBERO 공식 코드에 맞춰 연결한다. 두 카메라와 단일 팔 말단 제어에 대응하는 **LIBERO-Predict2-2B**에서 추가 학습을 시작한다.

실물에서는 사진의 **오른쪽 베이스·왼쪽 작업종이 배치**를 출발점으로 삼는다. 643×423 mm 종이 위에서 실제로 사용할 수 있는 영역을 먼저 찾고, 시뮬레이션 영역과의 폭·깊이 비율로 배율을 구한다. 영역 중심을 맞춰 초기 TCP의 후보 위치를 계산한 뒤 베이스 좌표로 바꾸고, 6축 자세·이동 경로·카메라 시야를 확인해 설치 위치를 확정한다. 최종 배율과 설치 좌표에는 도달 영역 경계와 작업면–베이스 보정값이 추가로 필요하다.

이 기본 배치를 유지하면서 task별 BDDL의 물체·출발·목표 조건을 실물 배치표에 대응시킨다. 시뮬레이터 안의 로봇까지 Mirobot으로 바꿀 때는 `MountedMirobot` 모델·그리퍼를 등록하고, 실측한 6축 시작 상태와 카메라 설정을 적용한다. 이후 실제 로봇 시연으로 정책을 추가 학습하고 같은 작업대에서 성공률을 평가한다.

현재 문서는 이 실험의 설계안이다. custom 기본 환경의 최종 설정, 실물 시연 학습과 성공률은 구현·실험 후 보고한다.

## 참고 자료

- 원논문: [LIBERO, arXiv:2306.03310](https://arxiv.org/abs/2306.03310) · [OpenVLA-OFT, arXiv:2502.19645](https://arxiv.org/abs/2502.19645) · [Cosmos Policy, arXiv:2601.16163](https://arxiv.org/abs/2601.16163)
- 환경 설정 코드: [LIBERO tabletop](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/problems/libero_tabletop_manipulation.py) · [LIBERO 환경 생성](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/env_wrapper.py) · [OpenVLA-OFT 환경 함수](https://github.com/moojink/openvla-oft/blob/e4287e94541f459edc4feabc4e181f537cd569a8/experiments/robot/libero/libero_utils.py) · [Cosmos Policy 환경·영상 처리](https://github.com/NVlabs/cosmos-policy/blob/18a2accadf4e7a3531e56754102af5a24d2316da/cosmos_policy/experiments/robot/libero/libero_utils.py) · [Cosmos Policy 관측·평가](https://github.com/NVlabs/cosmos-policy/blob/18a2accadf4e7a3531e56754102af5a24d2316da/cosmos_policy/experiments/robot/libero/run_libero_eval.py)
- 함수 분석 원문: [LIBERO 장면 조립·초기화](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/bddl_base_domain.py) · [OpenVLA-OFT 관측·실행](https://github.com/moojink/openvla-oft/blob/e4287e94541f459edc4feabc4e181f537cd569a8/experiments/robot/libero/run_libero_eval.py) · [Mirobot Gazebo 상위 launch](https://github.com/wlkata/RosForMirobot-master/blob/8a60a4ce16186ddbb9393e20bb904cbab61fc884/mirobot_gazebo/launch/mirobot_bringup_moveit.launch) · [Mirobot Xacro](https://github.com/wlkata/RosForMirobot-master/blob/8a60a4ce16186ddbb9393e20bb904cbab61fc884/mirobot_urdf_2/urdf/mirobot_urdf_2.xacro)
- 비교 환경과 설정 예제: [RoboCasa 환경 생성 코드](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/utils/env_utils.py) · [Isaac Sim URDF 가져오기 Python 예제](https://docs.isaacsim.omniverse.nvidia.com/latest/importer_exporter/import_urdf.html) · [WLKATA Mirobot Gazebo 실행 안내](https://github.com/wlkata/RosForMirobot-master/blob/8a60a4ce16186ddbb9393e20bb904cbab61fc884/README.md)
- 학습·모델: [Cosmos Policy 데이터 로더](https://github.com/NVlabs/cosmos-policy/blob/18a2accadf4e7a3531e56754102af5a24d2316da/cosmos_policy/datasets/libero_dataset.py) · [학습 설정](https://github.com/NVlabs/cosmos-policy/blob/18a2accadf4e7a3531e56754102af5a24d2316da/cosmos_policy/config/experiment/cosmos_policy_experiment_configs.py) · [LIBERO-Predict2-2B 체크포인트](https://huggingface.co/nvidia/Cosmos-Policy-LIBERO-Predict2-2B)
- 모델 비교: [RoboCasa 체크포인트](https://huggingface.co/nvidia/Cosmos-Policy-RoboCasa-Predict2-2B) · [ALOHA 체크포인트](https://huggingface.co/nvidia/Cosmos-Policy-ALOHA-Predict2-2B) · [ALOHA Planning 모델](https://huggingface.co/nvidia/Cosmos-Policy-ALOHA-Planning-Model-Predict2-2B)
- 시뮬레이션 확장: [custom task 생성](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/master/scripts/create_libero_task_example.py) · [물체 등록](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/master/libero/libero/envs/objects/turbosquid_objects.py) · [MuJoCo 모델링](https://mujoco.readthedocs.io/en/3.3.2/modeling.html)
- Mirobot 기본 환경·시작 자세: [공식 URDF·MoveIt 코드](https://github.com/wlkata/Wlkata_Mirobot_Ros2) · [WLKATA 제어 SDK](https://github.com/wlkata/WLKATA-Python-SDK-wlkatapython) · [Panda 말단 관측 구현](https://github.com/ARISE-Initiative/robosuite/blob/v1.4.0/robosuite/robots/single_arm.py)
- 실측·보정 방법: [TCP 위치](https://www.universal-robots.com/manuals/EN/HTML/SW10_12/Content/prod-usr-man/software/PolyScopeX/polyx-application/polyx-TCP_Position.htm) · [TCP 방향](https://www.universal-robots.com/manuals/EN/HTML/SW10_10/Content/prod-usr-man/software/PolyScopeX/polyx-application/polyx-TCP_Orientation.htm) · [카메라 내부 보정](https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html) · [solvePnP 자세 추정](https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html) · [hand–eye 보정](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html)
- 측정 오차의 평가: [NIST 측정 불확실성 지침](https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-2-classification-components-uncertainty) · [기기 사양·교정 정보의 활용](https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-4-type-b-evaluation-standard-uncertainty) · [불확실성 합성·보정](https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-5-combined-standard-uncertainty)
- D405 깊이 실측: [D405 사양](https://www.realsenseai.com/product-family/d405-series/) · [깊이·좌표 변환](https://dev.realsenseai.com/docs/projection-in-realsense-sdk-2-0/) · [RGB·깊이 정렬 구현](https://github.com/realsenseai/librealsense/blob/master/src/proc/align.cpp)
- Mirobot 모델 연결: [LIBERO 로봇 등록](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/robots/__init__.py) · [MountedPanda](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/robots/mounted_panda.py) · [robosuite 모델 인터페이스](https://github.com/ARISE-Initiative/robosuite/blob/v1.4.0/robosuite/models/robots/manipulators/manipulator_model.py)
