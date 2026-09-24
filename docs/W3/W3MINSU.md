[GitHub 저장소](https://github.com/williamjeon7/urop-mirobot-vla)

[Notion 정리본](https://aluminum-print-c83.notion.site/3-3e14291bfc4d804aa2e1c693bdaaaff1?pvs=74)

# 1. ROTATION.md

## 1. 회전을 적는 3가지 방법

1. 오일러각 $R_x, R_y, R_z$

$x,y,z$축 둘레를 차례로 돌린 각도, 어느 축부터 도는지, 돌아간 축을 기준으로 다시 도는지에 따라 규약이 갈린다. → 4번 참고

장점: 사람이 읽을 수 있다. ex) 20° 기울렸다.

단점: 순서 규약이 12가지, 짐벌락

순서 규약이 12가지인 이유: Euler angle에서 연속해서 같은 축을 돌리는 경우 제외

$(x,y,z)$에서 $xxy$ 이런 식으로 회전하면 $xx$는 한 번의 $x$ 회전으로 합칠 수 있기 때문이다.

Tait-Bryan angles: 세 축을 모두 한 번씩 사용

$XYZ, XZY, YXZ,YZX,ZXY,ZYX$ → 6가지

Proper Euler angles: 첫 번째 축과 세 번째 축이 같음

$XYX, XZX, YXY,YZY, ZXZ,ZYZ$ → 6가지

gimbal lock: Euler angle로 회전을 표현할 때 특정 자세에서 회전축 두 개가 겹쳐서, 서로 다른 회전을 구분할 수 없게 되는 현상

2. 쿼터니언 `wxyz`

4개짜리 단위 벡터, 회전을 곱으로 합칠 수 있고 특이한 자세가 없다

장점: 규약 문제, gimbal lock X, 합성과 보간이 안정적

단점: 사람이 못 읽는다.  $q = -q$, 저장 순서가 둘 → 5, 7번 참고

- **Position**: 어디에 있는가 → $(x, y, z)$

- **Orientation**: 어떤 방향으로 놓여 있는가 → 회전 상태

3. axis-angle $n_x, n_y, n_z$

축 단위벡터 × 각도(rad), 어느 축을 기준으로 몇 도 돌렸는지 표현

장점: gimbal lock X, 델타를 적기 쉽다

단점: 180° 근처에서 같은 자세를 두 가지로 적을 수 있다.

델타를 적기 쉽다 → 미분하여 현재 자세에서 얼마나 조금 더 회전할 지 표현하기 편하다

180° 근처에서 같은 자세를 두 가지로 적을 수 있다 → $r = \theta n$에서  $\pi n, -\pi n$이 같은 실제 rotation을 나타냄, z축으로 +180° 도는 것과 z축으로 -180° 도는 결과가 동일

---

## 2. 파이프라인 분석 (코드 어디에?)

1. Mirobot 보고 Cartesian(`XYZ RxRyRz`)  : 오일러각 (도)

robot/serial_bridge.py:180 참고

```python
cartesian = `re.search`(
    r"Cartesian coordinate\(XYZ RxRyRz\):([^,]+),([^,]+),([^,]+)",
    body,
)
if cartesian:
    parsed["mpos"] = [float(cartesian.group(i)) for i in range(1, 4)]
```

`re.search` : 해당 패턴이 처음 등장하는 위치를 찾는 함수

r : raw string, 정규표현식에서 `\(` 같은 백슬래시를 Python이 먼저 처리하지 않게 함.

`Cartesian coordinate\(XYZ RxRyRz\):` 문자열에서 정확히 `Cartesian coordinate(XYZ RxRyRz):`를 찾는다. `\(`, `\)`로 실제 괄호를 찾는다.

`([^,]+)` : 쉼표가 나오기 전까지의 문자를 전부 가져온다.

`[...]`: 대괄호 안의 문자 조건

`^,` : 쉼표 `,`가 아닌 문자

`+` : 1개 이상

→ Mirobot 응답 문자열에서 `Cartesian coordinate(XYZ RxRyRz):`를 찾고, 그 뒤에 있는 쉼표 구분 값 중 앞의 3개를 추출하는 코드다.

---

2. Mirobot 명령 `G0 ... A B C` : 오일러각 (도)

common/gcode.py:35

```python
return f"G0 X{x_mm:.2f} Y{y_mm:.2f} Z{z_mm:.2f} A{a:.2f} B{b:.2f} C{c:.2f}"
```

`X{x_mm:.2f}` → X 위치

`Y{y_mm:.2f}` → Y 위치

`Z{z_mm:.2f}` → Z 위치

`A{a:.2f}` → 첫 번째 회전값

`B{b:.2f}` → 두 번째 회전값

`C{c:.2f}` → 세 번째 회전값

G0: G-code에서 목표 위치로 빠르게 이동하는 명령

→ 현재 계산된 위치 X,Y,Z와 자세 A,B,C 값을 Mirobot이 이해할 수 있는 G-code 명령 문자열로 변환해서 반환한다.

---

3. LIBERO 정책 입력 proprio의 eef_quat

https://github.com/ARISE-Initiative/robosuite/blob/v1.4.1/robosuite/robots/single_arm.py

```python
@sensor(modality=modality)
`def eef_quat(obs_cache):`
    return T.convert_quat(
        self.sim.data.get_body_xquat(self.robot_model.eef_name),
        to="xyzw",
    )
```

`def eef_quat(obs_cache):` end-effector quaternion을 반환하는 함수

obs_cache : robosuite observable 시스템에서 다른  sensor 값을 참조할 때 사용하는 cache

self.sim.data : MuJoCo simulation state

self.robot_model.eef_name : 로봇의 end-effector body 이름

`get_body_xquat( … )` : 현재 simulation에서 end-effector body의 orientation quaternion을 가져옴

`T.convert_quat( … , to="xyzw")` : quaternion의 저장 순서 변환

→ MuJoCo는 기본적으로 wxyz 반환 → xyzw로 quaternion의 저장 순서를 바꿈

Why? LIBERO의 eef_quat observation은 xyzw 순서이기 때문에 맞춰줘야 한다.

---

4. LIBERO 데이터셋 ee_ori

https://github.com/openvla/openvla/blob/main/experiments/robot/libero/regenerate_libero_dataset.py

```python
`ee_states.append`(
    `np.hstack`(
        (
            obs["robot0_eef_pos"],
            T.quat2axisangle(obs["robot0_eef_quat"]),
        )
    )
)
```

`ee_states.append` : 매 timestep마다 현재 end-effector 상태를 하나씩 쌓는다

`np.hstack`: 여러 배열을 가로 방향으로 이어붙이는 함수

obs["robot0_eef_pos"] : 현재 robot0의 end-effector position→ [ $x,y,z$ ] 형태

T.quat2axisangle(…) : LIBERO quaternion $[x,y,z,w]$ 형태를 axis-angle 3차원 벡터로 변환

→ 각 timestep에서 LIBERO의 end-effector 위치 `robot0_eef_pos`와 quaternion 자세 `robot0_eef_quat`을 가져온다. 자세 quaternion은 `quat2axisangle()`을 통해 axis-angle로 변환하고, position 3차원과 orientation 3차원을 ``np.hstack`()`으로 합쳐 6차원 `ee_state`로 저장

```python
obs_grp.create_dataset("ee_states", data=np.stack(ee_states, axis=0))
obs_grp.create_dataset("ee_pos", data=np.stack(ee_states, axis=0)[:, :3])
obs_grp.create_dataset("ee_ori", data=np.stack(ee_states, axis=0)[:, 3:])
```

`np.stack(ee_states, axis = 0)` : 매 timestep마다 저장했던 $[x,y,z,rx,ry,rz]$ 형태의 벡터들을 세로로 쌓는다.

ex) 3 timestep

[

[x1, y1, z1, rx1, ry1, rz1],

[x2, y2, z2, rx2, ry2, rz2],

[x3, y3, z3, rx3, ry3, rz3]

]

[:, 3:] : 모든 행에서 3번째 인덱스 이후만 사용, rx ~ rz → orientation 부분만 추출

`obs_grp.create_dataset("ee_ori" , data=…)` : rx ~rz의 데이터를 HDF5 파일 안에 ee_ori라는 이름으로 저장

→ 지금까지 `ee_states`에 쌓아둔 6차원 end-effector 상태에서 뒤의 3개 orientation 값만 잘라서, HDF5 안에 `ee_ori`라는 이름으로 저장하는 코드

---

5. 정책 출력 액션 $\Delta r_x,\ \Delta r_y,\ \Delta r_z$ : axis-angle 델타

https://github.com/ARISE-Initiative/robosuite/blob/v1.4.1/robosuite/controllers/osc.py

```python
T.quat2mat(T.axisangle2quat(`delta[3:6]`))
```

→ delta의 회전 부분 3개를 axis-angle로 보고, 그걸 quaternion으로 바꾼 다음 최종적으로 회전행렬로 변환하는 코드

`delta[3:6]` : delta = [dx, dy, dz, drx, dry, drz]에서 axis-angle rotation delta [drx, dry, drz]만 사용

`T.axisangle2quat(…)` : axis-angle 벡터를 quaternion으로 변환 , $\Delta r \rightarrow \Delta q$

`T.quat2mat(…)`: quaternion을 3×3 회전행렬으로 변환

```text
`delta[3:6]`
→ axis-angle
→ quaternion
→ 3×3 rotation matrix
```

셋을 서로 직접 잇는 함수를 6개 만들면 엉키기 쉬워서 퀴터니언을 가운데 두고 양쪽만 만든다.

```text
Mirobot Euler
      │
      ▼
Quaternion (wxyz)
      ▲
      │
LIBERO axis-angle / Quaternion (xyzw)
```

표현끼리 직접 변환 함수를 전부 따로 만들기보다, 내부에서는 Quaternion(`wxyz`)을 중심 표현으로 사용하고 입출력 경계에서 필요한 표현으로 바꾼다.

---

## 3. 고려해야 할 4가지 layer 층

1. 표현

오일러각 ↔ 쿼터니언 ↔ axis-angle

2. 단위 규약

도/rad, extrinsic XYZ 순서 (4번)

3. 저장 순서

`wxyz`  ↔ `xyzw` (5번)

4. 기준 프레임

Mirobot top-down = $(0,0,0)$, LIBERO top-down = x축 180° (6번)

## 4. extrinsic XYZ - Mirobot의 오일러각 규약

오일러각 규약은 12가지

→축 순서 6가지(XYZ, XZY, YXZ, YZX, ZXY, ZYX) × 기준축 2가지

1. extrinsic(고정축): 회전축이 월드 좌표계에 고정, 월드 고정축 기준 회전

새로운 회전은 왼쪽에 붙는다.

Why?

현재 자세 : $p_{\text{world}} = R\,p_{\text{body}}$

월드 축 기준으로 새로운 회전 $Q$만큼 더 돌린다고 하면,

$p'_{\text{world}} = Q\,p_{\text{world}}$

원래 식에 대입

$p'_{\text{world}} = Q(R\,p_{\text{body}})$이므로 새로운 회전 $Q$가 왼쪽에 붙는다.

2. intrinsic(몸체축): 회전축이 물체와 같이 움직임, 몸체축 기준 회전

새로운 회전은 오른쪽에 붙는다.

Why?

현재 자세 :  $p_{\text{world}} = R\,p_{\text{body}}$

로컬 축 기준으로 새로운 회전 $Q$를 한다고 하면,

$p'_{\text{body}} = Q\,p_{\text{body}}$

현재 자세 $R$로 월드 좌표로 옮기면

$p'_{\text{world}} = R(Q\,p_{\text{body}})$이므로 새로운 회전 $Q$가 오른쪽에 붙는다.

따라서 extrinsic XYZ = intrinsic ZYX는 같은 회전이다.

수식

extrinsic XYZ: $R = R_z(r_z)\,R_y(r_y)\,R_x(r_x)$ ← Mirobot

쿼터니언으로 표현: $q_z \otimes q_y \otimes q_x$

intrinsic XYZ: $R = R_x(r_x)\,R_y(r_y)\,R_z(r_z)$

- **World**: 로봇 전체 작업공간의 기준 좌표계

- **gimbal lock**: $r_y = \pm 90^\circ$에서 생긴다.

Why?

$R = R_z(r_z)R_y(r_y)R_x(r_x)$를 회전행렬로 나타내면

$$
R =
\begin{bmatrix}
\cos r_z \cos r_y &
\cos r_z \sin r_y \sin r_x - \sin r_z \cos r_x &
\cos r_z \sin r_y \cos r_x + \sin r_z \sin r_x \\
\sin r_z \cos r_y &
\sin r_z \sin r_y \sin r_x + \cos r_z \cos r_x &
\sin r_z \sin r_y \cos r_x - \cos r_z \sin r_x \\
-\sin r_y &
\cos r_y \sin r_x &
\cos r_y \cos r_x
\end{bmatrix}
$$

짐벌락은 $r_y = \pm 90^\circ$에서 생긴다. 특히 $r_y = +90^\circ$이면

$$
R =
\begin{bmatrix}
0 & \sin(r_x-r_z) & \cos(r_x-r_z) \\
0 & \cos(r_x-r_z) & -\sin(r_x-r_z) \\
-1 & 0 & 0
\end{bmatrix}
$$

가 된다. 따라서 $r_x$와 $r_z$가 각각 따로 나타나는 것이 아니라 **$r_x-r_z$의 조합으로만 나타나므로** 두 값을 독립적으로 구분할 수 없다.

짐벌락에서는 실제 회전 자유도가 사라지는 것이 아니라, Euler angle 표현에서 두 축을 독립적으로 구분하지 못하게 된다.

---

## 5. `wxyz` vs `xyzw`

$w = \cos(\theta/2)$, $(x,y,z) = \text{axis}\cdot\sin(\theta/2)$

$w$ 자리를 잘못 쓰면 "회전량"과 "축"이 통째로 뒤바꿔서 유의해야 한다.

norm은 어느 쪽으로 읽어도 1이다. 쿼터니언은 단위 쿼터니언으로 정규화를 해서 사용하기 때문이다. 따라서 norm으로 유효한 쿼터니언인지 검증 불가능하다.

| 값 | `wxyz`로 읽으면 | `xyzw`로 읽으면 | norm |
|---|---|---|---|
| LIBERO 샘플 `proprio[5:9]` | 3.09°, 축 `−y` | **180.01°, 축 `+x`** | 둘 다 1.0000 |
| OASYS 첫 관측 | 2.18° | **180.14°, 축 `+x`** | 둘 다 1.0000 |
| `demo_0 states[5:9]` | **180.00°, 축 `x`** | 180.00°, 축 `y` | 둘 다 1.0000 |

같은 네 숫자를 순서만 다르게 해석해도 norm은 그대로 1이므로, norm만 확인해서는 저장 순서 오류를 잡을 수 없다.

LIBERO에서는 `xyzw` 순서로 쓰는 데 Mirobot(우리 실험)에서 `wxyz` 순서로 쓰는 이유

1. 수식과 대응이 직관적

Quaternion은 보통 $q=(w,x,y,z)$ 형태로 정의

내부도 `wxyz`로 두면 수학식과 코드 변수의 의미를 바로 대응시키기 쉽다.

2. MuJoCo 계열과 잘 맞음

MuJoCo의 body quaternion처럼 `wxyz` 계열 표현을 사용하는 시스템이 있다.

따라서 여러 변환 과정에서 내부 기준을 `wxyz`로 두면 중간 계산을 정리하기 편하다.

3. 내부 규약을 하나로 통일하기 위함

`wxyz`와 `xyzw`를 코드 곳곳에서 섞어 쓰면 에러 없이 잘못된 회전으로 해석 가능

내부는 `wxyz`로 고정하고, LIBERO와 데이터를 주고받을 때만 `xyzw` ↔ `wxyz` 변환을 수행

목표

Mirobot 오일러 ──▶ 쿼터니언(목표) ─┐

                                                                   ├─▶ 상대 회전 ──▶ axis-angle ──▶ action

LIBERO eef_quat (현재) ───────── ┘

---

## 6. 기준 프레임 - Mirobot, LIBERO

Mirobot과 LIBERO가 같은 실제 자세를 서로 다른 기준축으로 표현하기 때문에 고정 Frame $F$를 곱해 보정해준다.  즉 Mirobot에서 표현한 자세 $q_M$에, Mirobot Tool Frame과 LIBERO Tool Frame 사이의 고정된 180° 차이 F를 추가해서 LIBERO 기준 자세로 바꾼다.

ex) 그리퍼가 똑같이 아래를 봐도 Mirobot은 (0, 0, 0) (항등), LIBERO는 x축 $180^\circ$ 로 적는다.

$q_{\text{libero}} = q_{\text{mirobot}} \otimes F$     (오른쪽 곱, post) — 그리퍼(공구) 좌표축이 서로 돌아가 있다

→ 현재 Mirobot 자세에 대해 공구/몸체 좌표계 기준으로 추가 회전을 적용

$q_{\text{libero}} = F \otimes q_{\text{mirobot}}$     (왼쪽 곱,  pre)  — 월드 좌표축이 서로 돌아가 있다

→ 월드 좌표계 기준으로 전체 자세를 먼저 회전

- $\otimes$ : 회전은 위치처럼 더하는 게 아니라 회전의 합성으로 처리 → 곱셈 사용

---

홈 자세 하나 ($F$ 하나로는) 어느 방향인지 못 정한다.

$F$를 x축 $180^\circ$로 두고 두 방식을 비교

| Mirobot 자세 | post $q \otimes F$ | pre $F \otimes q$ | 차이 |
|---|---|---|---|
| 홈 `(0,0,0)` | 180°, 축 `[1, 0, 0]` | 180°, 축 `[1, 0, 0]` | **0.00°** |
| `Ry +10°` | 180°, 축 `[0.996, 0, -0.087]` | 180°, 축 `[0.996, 0, +0.087]` | **20.00°** |
| `Rz +30°` | 180°, 축 `[0.966, +0.259, 0]` | 180°, 축 `[0.966, -0.259, 0]` | **60.00°** |

자세가 커질수록 틀렸을 때 오차가 회전각의 2배로 벌어진다. (부호가 뒤집히기 때문)

→ 따라서 궤적에 자세 변화가 필요하다.

→ 일반형 $q_{\text{libero}} = W \otimes q_{\text{mirobot}} \otimes T$ ($W$: 월드 정렬, $T$: 공구 정렬) 사용

→ 홈 자세 하나로는 둘의 곱만 알 수 있고, 분리하려면 자세를 바꿔 가며 비교가 필요

→ 비교하는 방법

| 방법 | 확인 내용 |
|---|---|
| 축 대응표 | LIBERO에서 `Δrx`, `Δry`, `Δrz`를 하나씩 넣어 그리퍼가 기우는 방향을 보고 Mirobot의 `Rx+`, `Ry+`, `Rz+`와 비교 |
| 두 후보 재생 | 같은 기울어진 자세를 post / pre 두 방식으로 변환해 Panda에서 비교 |

---

## 7. 부호 연속성 - $q$와 $-q$는 같은 자세

Quaternion은 부호가 반대여도 같은 실제 자세를 나타낼 수 있다.

$R(q) = R(-q)$

즉 `q`와 `-q`는 숫자는 다르지만 로봇이 바라보는 실제 Orientation은 같다.

문제는 trajectory에서 실제 자세는 부드럽게 변하고 있는데 Quaternion 부호가 갑자기 바뀌면, 값 자체는 크게 튄 것처럼 보일 수 있다는 점이다. 이런 불연속은 Policy 입력이나 Orientation 오차 계산에서 문제가 될 수 있다.

실제 Orientation 차이는 다음 식으로 계산한다.

$\Delta\theta = 2\arccos\!\left(\left|q_1 \cdot q_2\right|\right)$

내적에 절댓값을 사용하는 이유도 `q`와 `-q`를 같은 자세로 보기 위해서다.

우리 환경에서는 `w ≥ 0`으로 부호를 고정하는 방식은 사용하지 않았다. Top-Down 자세가 X축 약 180° 회전 근처라서:

$w = \cos(90^\circ) \approx 0$

이 되고, 작은 노이즈만 있어도 `w`의 부호가 쉽게 바뀔 수 있기 때문이다.

그래서 이전 Quaternion과 현재 Quaternion을 직접 비교해서 부호를 맞춘다.

$\operatorname{dot}(q_i, q_{i-1}) < 0$

이면 현재 Quaternion의 부호를 뒤집는다.

$q_i \leftarrow -q_i$

이렇게 해도 실제 Orientation은 변하지 않고, 이전 값과 더 가까운 Quaternion 표현을 사용하게 되므로 trajectory가 연속적으로 유지된다.

Orientation 오차를 계산할 때도 같은 방식으로 현재 Quaternion과 목표 Quaternion의 내적을 확인하고, 내적이 음수이면 목표 Quaternion의 부호를 먼저 뒤집은 뒤 오차를 계산한다.

다만 이 방법은 두 Waypoint 사이의 회전 변화가 너무 크면 실제 회전 방향을 판단하기 어렵기 때문에, 실험에서는 Waypoint 사이 자세 변화를 가능하면 90° 이하로 유지한다.

### 핵심

- `q`와 `-q`는 같은 실제 자세이다.

- 실제 자세는 같아도 Quaternion 숫자는 갑자기 반전될 수 있다.

- `w ≥ 0` 방식은 180° 근처 자세에서 불안정할 수 있다.

- 따라서 이전 Quaternion과의 내적을 이용해 부호를 맞춘다.

- $\operatorname{dot}(q_i, q_{i-1}) < 0$이면 $q_i \leftarrow -q_i$로 처리한다.

---

# 2. CONTROL.md

## 1. 한 스텝 정리

```text
Panda (LIBERO)
Delta Action
→ 현재 자세를 기준으로 목표 생성
→ 목표와 현재의 차이로 힘 계산
→ 관절 토크 생성
→ 한 스텝 동안 목표의 일부만 이동

Mirobot
G0 X Y Z A B C
→ IK
→ 목표 관절 각도 계산
→ 스텝 모터 구동
→ 지정한 목표에 도착한 뒤 정지
```

---

## 2. 비교

| 항목 | Panda (LIBERO) | Mirobot |
|---|---|---|
| 명령 방식 | 현재 자세를 기준으로 한 **변화량(delta)** 을 받음 (`control_delta = true`) | **절대 좌표**를 받음 (`G90`, `M20`) |
| 명령 단위 | 입력은 `[-1, 1]` 범위의 정규화 값이며, 컨트롤러에서 m·rad 단위로 변환 | 위치는 mm, 회전은 degree |
| 내부 처리 | 목표 자세 계산 → 힘 계산 → 관절 토크 생성 | IK 계산 → 관절 각도 계산 → 스텝 모터 구동 |
| 한 스텝 뒤 | 목표까지 한 번에 가지 않고 약 25% 정도 이동 | 지정한 목표 위치까지 이동한 뒤 정지 |
| 도착 확인 | Observation을 다시 읽어 현재 자세와 목표 자세의 오차를 확인 | **상태 조회 명령 `?`를 보내 `Idle` 상태인지 확인** |
| 움직임이 막히면 | 목표 방향으로 힘이 계속 걸린 상태로 멈춤 | 모터는 계속 움직이려 하기 때문에 스텝 손실이 발생할 수 있음 |
| 위치 기준점 | **파지점(`grip_site`)** 기준. `eef_pos`가 손가락 사이 파지점을 나타냄 | **플랜지** 기준. Home 좌표가 로봇 링크 길이 합과 일치 |
| 회전 중심 | **파지점(`grip_site`)** 기준으로 회전 | **플랜지** 기준으로 회전 |
| 명령하지 않은 축 | 다른 축도 약 10% 이하로 함께 움직일 수 있음 | 자세만 변경했을 때 위치 변화가 약 0.07 mm 이내 |

- **플랜지**: 팔 끝에서 공구를 붙이는 면이다.

- **파지점**: 그리퍼 손가락 사이의 무는 점

→ Panda 로봇과 Mirobot의 좌표는 파지점, 플랜지로 다르므로 변환할 때는 플랜지 ↔ 플랜지로 맞춘다.

```text
Panda
플랜지 ── 약 97 mm ── 파지점(grip_site)

Mirobot
플랜지 ── L_M(미측정) ── 파지점
```

현재는 두 로봇의 **플랜지 ↔ 플랜지**를 기준으로 trajectory를 맞추고, 파지점까지 맞추려면 Mirobot의 `L_M`을 추가로 측정해야 한다.

---

## 3. 손끝 보정이 왜 필요한가

Panda와 Mirobot은 Cartesian 좌표에서 **위치의 기준점이 서로 다르다.**

Panda(LIBERO)의 `eef_pos`는 그리퍼 손가락 사이의 **파지점(`grip_site`)**을 나타낸다.

즉 실제로 물체를 집는 손끝 위치를 End-Effector 위치로 사용한다.

반면 Mirobot의 Cartesian 좌표는 **플랜지**를 기준으로 한다.

플랜지는 로봇 팔 끝에서 그리퍼가 장착되는 면으로, 실제 물체를 잡는 지점보다 뒤쪽에 있다.

Panda에서는 플랜지에서 파지점까지 공구 축 방향으로 약 **97 mm**의 거리가 있다.

따라서 Panda의 `eef_pos`와 Mirobot의 Cartesian 좌표를 그대로 맞추면, 숫자가 같아도 실제 그리퍼의 위치는 서로 맞지 않는다.

이 때문에 현재 변환에서는 Panda의 `eef_pos`만 사용하는 것이 아니라, Panda 플랜지 위치인 `robot0_right_hand`를 `flange_pos`로 따로 기록한다.

즉 현재 변환 기준은:

`Panda 플랜지 ↔ Mirobot 플랜지`

로 맞춘다.

또한 두 로봇은 **회전 중심도 다르다.**

- Panda: 파지점(`grip_site`)을 중심으로 회전

- Mirobot: 플랜지를 중심으로 회전

따라서 두 로봇의 플랜지 위치와 자세를 동일하게 맞추더라도, 자세를 기울이면 실제 손끝이 지나가는 궤적은 서로 달라질 수 있다.

현재 방식에서는 Mirobot이 Panda의 **플랜지가 이동한 경로**를 따라가게 되고, 그리퍼 손끝의 궤적까지 완전히 같아지는 것은 아니다.

실제로 파지점까지 정확하게 맞추려면 Mirobot에서도:

`플랜지 → 파지점`

사이의 길이, 즉 Mirobot의 tool offset을 알아야 한다.

현재 Mirobot의 정확한 플랜지-파지점 길이는 아직 측정하지 않았기 때문에 우선 플랜지 기준으로 변환하고 있으며, 이후 손끝 위치까지 맞추려면 이 길이를 측정해서 추가 보정해야 한다.

### 파지점 ↔ 파지점 보정 방법

현재는 Panda와 Mirobot의 플랜지 위치를 서로 맞추고 있다.

하지만 실제 물체를 집는 위치까지 맞추려면 각 로봇의 플랜지에서 파지점까지의 tool offset을 고려해야 한다.

Panda는 플랜지에서 파지점까지의 거리가 약 97 mm이고, Mirobot도 플랜지에서 파지점까지의 길이 $L_M$을 측정하면 같은 방식으로 보정할 수 있다.

플랜지 위치를 $p_{\text{flange}}$, 현재 자세의 공구축 방향을 $z_{\text{tool}}$이라고 하면 파지점 위치는:

$$
p_{\text{grip}} = p_{\text{flange}} + z_{\text{tool}} \times L
$$

로 계산한다.

여기서 $z_{\text{tool}}$은 현재 Quaternion을 회전행렬로 바꿨을 때 공구의 Z축 방향이다.

즉 로봇이 기울어지면 단순히 World Z 방향으로 길이를 더하는 것이 아니라, **현재 기울어진 공구축 방향으로 $L$만큼 이동**해야 한다.

Panda: (플랜지 ↔ 파지점 97mm)

$$
p_{\text{grip},P} = p_{\text{flange},P} + z_P \times 0.097
$$

Mirobot:

$$
p_{\text{grip},M} = p_{\text{flange},M} + z_M \times L_M
$$

이렇게 두 로봇의 파지점 위치를 각각 계산한 뒤:

$$
p_{\text{grip},P} \leftrightarrow p_{\text{grip},M}
$$

이 서로 같도록 Mirobot의 플랜지 목표를 역으로 계산하면 된다.

Mirobot의 목표 플랜지 위치는:

$$
p_{\text{flange},M} = p_{\text{grip,target}} - z_M \times L_M
$$

이 된다.

즉 전체 과정은:

```text
Panda 파지점 목표

→ Mirobot에서 같은 파지점 목표 설정

→ Mirobot 공구축 방향으로 L_M만큼 뒤로 이동

→ 실제로 명령할 Mirobot 플랜지 위치 계산
```

---

## 4. Panda를 목표 자세까지 보내는 방법

Panda의 Action은 절대 좌표가 아니라 **현재 자세를 기준으로 한 변화량(delta)**이다. 그래서 Mirobot처럼 목표 좌표를 한 번 보내고 기다리는 방식만으로는 원하는 위치까지 보낼 수 없다.

시뮬레이션에서 x 방향으로 `0.5`의 Action을 주고, 아래 세 가지 방법을 비교했다. `0.5`는 목표 오프셋 25 mm에 해당한다. (Panda의 위치 Action은 정규화된 값, 1.0이 0.05m에 대응)

| 방식 | 결과 |
|---|---|
| 한 번 주고 기다리기 | 약 5.9 mm에서 멈춤 |
| 같은 Action을 계속 주기 | 멈추지 않고 계속 이동 |
| 목표를 고정하고 매 스텝 다시 계산 | 약 25 mm에서 정지 |

### ① 한 번 주고 기다리기

Panda의 목표는 매 스텝 **현재 위치 + Action**으로 다시 계산된다.

$$
\text{현재} + \text{액션}
$$

처음 `0.5`를 입력하면 Panda는 현재 위치보다 25 mm 앞을 목표로 잡는다. 하지만 한 스텝 동안 실제로는 목표까지 전부 이동하지 못한다. 이후 Action을 `0`으로 바꾸면 25 mm 앞의 기존 목표가 유지되는 것이 아니라, 그때의 현재 위치가 새로운 목표가 된다. 따라서 더 이상 앞으로 이동하려는 힘이 생기지 않고 남아 있던 움직임이 감쇠되면서 약 5.9 mm 이동한 지점에서 멈춘다.

즉 Panda에서는 **Delta Action을 한 번 주는 것만으로 절대 목표까지 이동시킬 수 없다.**

### ② 같은 Action을 계속 주기

반대로 매 스텝 `0.5`를 계속 주면 목표가 현재 위치보다 계속 앞에 새로 만들어진다.

실험에서는 10스텝에 50.9 mm, 20스텝에 115.1 mm, 40스텝에 240.2 mm까지 이동했다.

따라서 이 방식에는 특정 위치에 **도착한다**는 개념이 없다. 같은 Action을 계속 주면 목표도 계속 앞쪽으로 이동하므로 로봇도 계속 움직인다.

### ③ 목표를 고정하고 매 스텝 다시 계산

우리가 사용할 방식이다.

최종 목표 위치는 고정하고, 매 스텝 현재 위치를 다시 읽은 뒤 남은 거리를 이용해 Action을 계산한다.

$$
\frac{\text{목표} - \text{현재}}{0.05}
$$

목표에 가까워질수록 Action도 자연스럽게 작아진다.

`0.50 → 0.22 → 0.01`

실험에서는 약 9스텝 만에 목표 1 mm 안쪽까지 들어왔고, 최대 약 2 mm 정도 초과한 뒤 목표 근처에서 멈췄다.

여러 축을 동시에 움직일 때는 Action의 각 성분을 따로 잘라내면 원래 이동 방향이 달라질 수 있으므로 **방향은 유지하면서 전체 크기만 줄이는 방식**이 필요하다.

LIBERO 데모를 만들 때는 사람이 SpaceMouse를 계속 움직이면서 Panda를 직접 조종한다.

사람이 로봇의 움직임을 보고,

"조금 더 오른쪽", "조금 더 앞으로"처럼 계속 다음 입력을 주기 때문에

사람이 직접 로봇의 움직임을 보면서 수정하는 구조이다.

반면 Policy 평가에서는 사람이 조종하지 않는다.

Policy가 현재 로봇의 상태와 카메라 영상을 보고

"다음 순간에는 이만큼 움직여라"라는 Delta Action을 출력한다.

그 Action을 `env.step()`에 넣으면 시뮬레이터에서 Panda가 한 스텝 움직이고,

새로운 상태가 다시 Policy에 들어간다.

즉:

사람이 조종할 때:

현재 상태 확인 → 사람이 SpaceMouse 조작 → Panda 이동 → 사람이 다시 확인

Policy 평가할 때:

현재 관측 → Policy가 Action 출력 → `env.step()` → Panda 이동 → 새로운 관측

MimicGen처럼 정해진 자세열을 재생하는 경우에도, 우리 방식과 마찬가지로 **절대 목표를 계속 추적하면서 20 Hz로 Delta Action으로 변환**한다.

따라서 이번 실험에서는 ③번 방식을 사용하되, 정해진 시간이 지나면 다음 목표로 넘어가는 것이 아니라 **현재 목표에 도착했는지 확인한 뒤** 다음 목표로 넘어간다.

---

## 5. 우리 작업에 주는 영향

Panda와 Mirobot의 제어 방식 차이는 trajectory를 어느 방향으로 옮기는지에 따라 영향이 다르다.

| 방향 | 영향 |
|---|---|
| LIBERO → Mirobot | 영향 없음 |
| Mirobot → LIBERO | Closed-loop 필요 |
| Policy → Mirobot | 별도 고려 필요 |

### 1. LIBERO → Mirobot

이 방향에서는 큰 문제가 없다.

우리가 Mirobot으로 보내는 것은 Panda에 입력했던 Delta Action이 아니라 **Panda가 실제로 있었던 자세**이다.

즉 시뮬레이션에서 Panda가 실제로 이동한 위치와 자세를 기록한 뒤, 이를 Mirobot의 절대 좌표로 변환한다.

따라서 Panda가 한 스텝에서 목표의 약 25%만 이동하는 특성은 이미 기록된 실제 자세에 반영되어 있다.

### 2. Mirobot → LIBERO

이 방향에서는 Panda의 제어 특성을 고려해야 한다.

Mirobot은 절대 좌표를 주면 목표까지 이동하고 멈추지만, Panda는 한 번의 Delta Action만으로 목표까지 가지 않는다.

따라서 매 스텝:

1. Panda의 현재 자세를 다시 읽고

2. 현재와 목표의 차이를 계산하고

3. Delta Action을 다시 만든 뒤

4. `env.step()`을 실행한다.

이 과정을 목표에 도착할 때까지 반복해야 한다.

즉 **현재 상태를 계속 확인하면서 목표를 추적하는 Closed-loop 제어**가 필요하다.

### 3. Policy → Mirobot

이 부분은 현재 범위 밖이지만, 이후 실제 로봇에 Policy를 연결할 때 중요하다.

Policy의 Action에는 Panda Controller의 특성이 이미 포함되어 있다. Panda는 한 스텝에서 목표의 약 25%만 움직이기 때문에, 이 변화량을 그대로 Mirobot에 적용하면 Mirobot이 한 스텝에 약 4배 크게 움직일 수 있다.

따라서 Policy를 Mirobot에 직접 연결하려면 Panda와 Mirobot의 움직임 차이를 추가로 고려해야 한다.

---

## 6. 왜 이렇게 다른가

Panda와 Mirobot의 제어 방식이 다른 이유는 **로봇의 목적과 하드웨어가 다르기 때문**이다.

### 1. Panda

Panda는 사람과 같이 사용하는 로봇이라, 충돌했을 때 힘이 제한될 수 있도록 **임피던스 제어**를 사용한다.

목표를 가상의 스프링으로 당기는 것처럼 움직이기 때문에, 한 번에 목표로 이동하는 것이 아니라 여러 스텝에 걸쳐 부드럽게 접근한다.

장애물에 막히면 목표 방향으로 힘이 걸린 상태에서 멈출 수 있다.

LIBERO 데모와 Cosmos Policy의 Action에는 이러한 **Panda Controller의 특성이 이미 포함되어 있다.**

### 2. Mirobot

Mirobot은 교육용 스텝 모터 로봇으로 **위치 제어**를 사용한다.

절대 좌표를 받으면 IK를 통해 필요한 관절 각도를 계산하고, 스텝 모터를 해당 각도까지 움직인 뒤 멈춘다.

Panda와 달리 힘을 느끼지 못하고 되먹임도 없다. 따라서 장애물에 걸리더라도 모터는 목표 각도까지 움직이려고 하며, 이 과정에서 스텝을 잃을 수 있다.

대신 목표 위치까지 이동하고 멈추며, 같은 명령을 주면 같은 위치에 서는 방식이다.

결국 **Panda는 목표를 힘으로 따라가는 방식**이고, **Mirobot은 정해진 위치까지 이동하는 방식**이라는 차이가 있다. 이 때문에 두 로봇의 trajectory를 변환할 때는 좌표뿐 아니라 제어 방식의 차이도 함께 고려해야 한다.

---

# 3. CONVERSION.md → Mirobot ↔ LIBERO 좌표 변환 정리

Mirobot과 LIBERO는 같은 로봇 자세를 서로 다른 방식으로 표현한다.

그래서 trajectory를 한쪽에서 다른 쪽으로 옮기려면 단순히 좌표 숫자만 바꾸는 것이 아니라 **회전 표현 방식, Quaternion 순서, 기준 프레임, 위치 단위와 기준점**을 같이 맞춰줘야 한다.

---

## 1. 변환할 때 맞춰야 하는 것

두 로봇 사이에서 실제로 변환해야 하는 부분은 크게 **위치와 자세**이다.

| 항목 | 변환 여부 | 내용 |
|---|---|---|
| 자세 | O | Euler ↔ Quaternion, `wxyz` ↔ `xyzw`, 기준 프레임 `F` 변환 |
| 위치 | O | m ↔ mm, 시작 위치 정렬, 플랜지 ↔ 파지점 차이 처리 |
| 축 방향 | X | 두 로봇의 World 축 방향은 동일 |
| 시간·속도 | X | 현재는 waypoint의 위치와 자세를 중심으로 비교 |

두 환경의 World 축 방향은 같다.

- `X ↔ x`: 앞

- `Y ↔ y`: 왼쪽

- `Z ↔ z`: 위

따라서 위치를 옮길 때 축 자체를 바꾸거나 부호를 반대로 만들 필요는 없다.

결국 중요한 것은 **같은 실제 위치와 자세를 각 로봇의 표현 방식에 맞게 다시 표현하는 것**이다.

- **Waypoint**: 로봇이 trajectory를 따라가면서 순서대로 도달해야 하는 중간 목표 자세

---

## 2. LIBERO 자세를 Mirobot으로 옮기기

LIBERO에서 기록한 Panda의 waypoint를 실제 Mirobot이 실행할 수 있는 G-code로 변환하는 과정이다.

전체적으로는 **회전 변환 → 위치 변환 → G-code 생성** 순서로 진행된다.

### 회전 변환

LIBERO에서 저장된 Quaternion은 `xyzw` 순서이다.

먼저 이를 내부에서 사용하는 `wxyz` 순서로 바꾼다.

```text
LIBERO Quaternion (xyzw)

→ wxyz

→ 기준 프레임 변환

→ Euler angle

→ Mirobot A B C
```

LIBERO와 Mirobot은 같은 top-down 자세를 서로 다르게 표현하기 때문에 프레임 차이도 보정해야 한다.

LIBERO → Mirobot 방향에서는 다음 변환을 사용한다.

$$
q \otimes F^{-1}
$$

여기서 `F`는 x축 180° 회전이다.

Mirobot에서는 top-down 자세가 `(0, 0, 0)`이지만, LIBERO에서는 같은 자세가 x축 180° 회전으로 표현되기 때문에 이 차이를 없애주는 것이다.

이후 Quaternion을 Mirobot이 사용하는 extrinsic XYZ Euler angle로 바꿔 `A B C` 값으로 사용한다.

### absolute와 relative

회전을 옮기는 방법은 두 가지가 있다.

- **absolute**: LIBERO에서 기록된 실제 자세를 그대로 사용

- **relative**: 처음 자세를 기준으로 이후에 변한 회전만 사용

relative를 사용하면 Panda가 처음부터 가지고 있던 약 3.3°의 기울기는 제외하고, trajectory 중 실제로 발생한 회전 변화만 Mirobot에 전달할 수 있다.

### 위치 변환

두 로봇은 절대 좌표의 원점이 다르기 때문에 좌표값 자체를 그대로 대응시키지 않는다.

대신 **시작점에서 얼마나 이동했는지**를 구한 다음 그 변위만 Mirobot에 옮긴다.

예를 들어 Panda 플랜지 위치가:

```text
-0.2062 m → -0.1464 m
```

로 바뀌었다면 이동량은:

```text
(-0.1464) - (-0.2062) = +0.0598 m → +59.81 mm
```

이다.

이 값을 Mirobot Home 위치에 더하면:

```text
198.67 + 59.81 = 258.48 mm
```

가 된다.

즉 기준은:

```text
Panda 시작 플랜지 ↔ Mirobot Home
```

으로 잡고, **각 로봇의 절대 좌표가 아니라 시작점에서의 이동량을 맞추는 방식**이다.

최종적으로 위치와 회전을 합치면 다음과 같은 G-code가 만들어진다.

```text
G0 X258.48 Y0.43 Z222.31 A0.01 B14.94 C-0.06
```

---

## 3. Mirobot 자세를 LIBERO로 옮기기

반대 방향은 앞의 과정을 거의 역순으로 진행한다.

다만 Mirobot은 절대 좌표를 입력하면 그 위치까지 이동하지만, Panda는 Delta Action을 받기 때문에 **좌표를 변환한 뒤 목표를 따라가는 과정이 추가로 필요하다.**

```text
Mirobot X Y Z / A B C

→ Euler → Quaternion

→ 기준 프레임 변환

→ 위치 변환

→ 플랜지 → 파지점

→ Delta Action 계산

→ 목표까지 반복
```

### 회전 변환

Mirobot의 `A B C`는 extrinsic XYZ Euler angle이므로 먼저 Quaternion으로 변환한다.

$$
q_z \otimes q_y \otimes q_x
$$

그다음 Mirobot 기준 자세를 LIBERO 기준으로 바꾼다.

$$
q \otimes F
$$

LIBERO → Mirobot에서 `F⁻¹`을 사용했다면, 반대 방향에서는 `F`를 사용한다.

### 위치 변환

Mirobot에서는 현재 위치에서 Home 위치를 빼서 이동량을 구한다.

그 값을 mm에서 m로 바꾸고 Panda의 시작 플랜지 위치에 더한다.

```text
Mirobot 현재 위치

→ Home 기준 이동량

→ mm → m

→ Panda 시작 플랜지에 더함
```

즉 이 방향에서도 마찬가지로 **절대 좌표 자체보다 시작점에서 얼마나 움직였는지**를 기준으로 변환한다.

관절 각도나 링크 길이가 아니라 End-Effector가 작업 공간에서 얼마나 이동했는지는 맞추는 것이다.

### 플랜지와 파지점 차이

Mirobot의 Cartesian 좌표는 플랜지를 기준으로 하지만, Panda에서 실제로 제어하는 위치는 파지점이다.

그래서 `flange_to_grip`을 사용해 Panda 플랜지 위치를 파지점 기준으로 바꿔줘야 한다.

현재 Panda에서는 플랜지와 파지점 사이에 97 mm의 차이가 있다.

### Panda를 목표까지 이동시키기

Panda는 절대 목표를 한 번 보내서 움직이는 방식이 아니기 때문에 매 스텝 현재 자세를 다시 확인하면서 Action을 계산한다.

```text
servo_action = (목표 − 현재) / (0.05m, 0.5rad)
```

Action이 너무 커질 경우 각 축을 각각 잘라내지 않고 **이동 방향은 유지하면서 전체 크기만 줄인다.**

그리고 다음 조건을 만족하면 해당 waypoint에 도착했다고 판단한다.

```text
위치 오차: 2 mm 이내

자세 오차: 1° 이내

한 스텝 이동량:

위치 0.3 mm 이하

자세 0.05° 이하
```

즉 목표 근처에 들어온 것뿐 아니라 **실제로 움직임이 거의 멈췄는지까지 확인한 후 다음 waypoint로 넘어간다.**

---

## 4. 코드에서는 어디서 처리하나

변환 과정은 역할에 따라 여러 파일로 나눠져 있다.

| 파일 | 역할 |
|---|---|
| `common/rotation.py` | Euler, Quaternion, axis-angle 변환과 프레임 변환 |
| `common/workspace.py` | 위치 변환, Home 좌표, 플랜지 ↔ 파지점 변환 |
| `common/servo.py` | Panda의 Delta Action 계산과 도착 여부 판단 |
| `tools/libero_compound_rollout.py` | LIBERO에서 waypoint 기록 |
| `tools/libero_to_mirobot_gcode.py` | LIBERO waypoint를 Mirobot G-code로 변환 |
| `tools/run_gcode.py` | 실제 Mirobot에서 G-code 실행 |
| `tools/roundtrip_check.py` | Mirobot 결과를 다시 LIBERO로 변환해 비교 |
| `tools/libero_follow.py` | 변환된 목표를 Panda가 따라가도록 실행 |

### 회전 관련 함수

`common/rotation.py`에서는 회전 표현을 서로 바꾸거나 두 로봇의 프레임 차이를 처리한다.

| 함수 | 역할 |
|---|---|
| `euler_xyz_deg_to_quat()` | Mirobot Euler → Quaternion |
| `quat_to_euler_xyz_deg()` | Quaternion → Mirobot Euler |
| `quat_wxyz_to_xyzw()` / `quat_xyzw_to_wxyz()` | Quaternion 저장 순서 변경 |
| `axis_angle_to_quat()` / `quat_to_axis_angle()` | axis-angle ↔ Quaternion |
| `enforce_sign_continuity()` | Quaternion 부호가 갑자기 뒤집히는 현상 방지 |
| `quat_error_axis_angle()` | 현재 자세와 목표 자세의 회전 차이 계산 |
| `mirobot_to_libero_quat()` / `libero_to_mirobot_quat()` | Mirobot ↔ LIBERO 프레임 변환 |

Mirobot → LIBERO:

$$
q \otimes F
$$

LIBERO → Mirobot:

$$
q \otimes F^{-1}
$$

정리하면:

- `rotation.py`: 자세 표현과 기준 프레임 처리

- `workspace.py`: 위치와 기준점 처리

- `servo.py`: Panda가 실제 목표를 따라가도록 제어

로 역할이 나뉜다.

---

## 5. 변환이 제대로 되는지 확인한 결과

변환 결과는 계산뿐 아니라 실제 Mirobot까지 포함해서 확인했다.

| 확인 방법 | 결과 |
|---|---|
| 변환 → 역변환 | 위치 **0.007 mm**, 자세 **0.006°** |
| LIBERO → Mirobot 좌표 → LIBERO | **2.34 mm, 0.34°** |
| 실제 Mirobot 실행 → LIBERO 역변환 | **0.30 mm, 0.05°** |
| 프레임 회전 `F` 확인 | Mirobot `A15`, `B15`, `C20`과 LIBERO의 회전 방향이 일치 |

계산상 변환을 다시 역변환했을 때는 거의 원래 값으로 돌아왔다.

실제 Mirobot을 움직인 뒤 그 값을 다시 LIBERO로 변환했을 때도 위치 0.30 mm, 자세 0.05° 정도의 차이로 돌아오는 것을 확인했다.

다만 **왕복 오차가 작다고 해서 프레임 변환 `F`까지 맞다고 볼 수는 없다.**

잘못된 변환을 적용하고 역변환에서도 같은 규칙으로 되돌리면 결과적으로 원래 값으로 돌아올 수도 있기 때문이다.

그래서 `F`는 왕복 오차와 별개로 실제 Mirobot의 `A`, `B`, `C` 회전 방향을 LIBERO와 직접 비교해서 확인했다.

---

## 6. 아직 확인하거나 보정해야 할 부분

현재 좌표와 회전 변환은 동작하지만 Panda와 Mirobot의 구조 자체가 다르기 때문에 몇 가지 차이는 남아 있다.

| 항목 | 남은 내용 |
|---|---|
| 회전 중심 | Panda는 파지점, Mirobot은 플랜지 중심으로 회전 |
| Mirobot 플랜지 → 파지점 길이 | 아직 측정하지 않음 |
| Mirobot Z 보고값 | 명령한 Z보다 낮게 보고되는 현상 확인 필요 |
| absolute / relative | 파일과 실행 옵션 사이에서 기준을 맞춰야 함 |

가장 중요한 것은 **실제 파지점의 위치**이다.

현재는 Panda와 Mirobot의 플랜지를 기준으로 trajectory를 대응시키고 있다.

하지만 두 로봇에서 실제 물체를 잡는 손끝까지 같은 위치로 맞추려면 Mirobot의 플랜지에서 파지점까지의 길이를 직접 측정해서 추가로 보정해야 한다.

또 Mirobot에서 명령한 Z와 보고되는 Z 사이에 차이가 있는데, 이것이 실제 위치 차이인지 단순히 내부 보고값의 차이인지는 아직 확인하지 못했다.

- Z: 로봇 플랜지의 수직 높이 좌표(mm)

현재까지는 **회전 표현 변환, 좌표 변환, 실제 Mirobot 실행, 다시 LIBERO로 돌아오는 왕복 변환까지 확인한 상태**이고, 이후에는 실제 손끝 위치와 물리적인 오차를 추가로 확인하면 된다.