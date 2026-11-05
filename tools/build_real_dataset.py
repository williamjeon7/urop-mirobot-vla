"""실물 녹화 폴더 → Cosmos 학습 데이터 폴더 한 번에 (W10, docs/W10/DATA_CHECK.md).

`tools/inventory_recordings.py` 로 `ready` 녹화를 고르고, 동료 변환기(`export_real_hdf5.export_episode`)로 HDF5 를 만든 뒤
구조·T5 를 검사한다. 이미 만든 HDF5 는 입력이 같으면 다시 만들지 않고 확인만 한다 (`skip_existing`).

* 색 — 녹화마다 **자기 색**을 target 으로 쓴다(점검에서 폴더 색 = metadata 색 = layout target 을 확인). 변환기 CLI 의
  `--target` 이 한 번에 넣은 모든 녹화에 붙는 문제를 피한다
* 허용치 기록 — 정렬 보고서에 실제 허용치가 없어 변환기가 HDF5 에 40 을 적는다. `--max-frame-ms` 값으로 고쳐 적는다
* T5 · 통계 — 없으면 `--t5-source` · `--stats-source` 에서 복사한다 (지시문 세 문장, 공식 LIBERO 통계)
* 남은 확인 — Cosmos 로더(`tools.check_cosmos_dataset`)와 학습 설정(`train --dryrun`)은 끝에 명령을 찍는다

    cosmos-policy/.venv/bin/python -m tools.build_real_dataset Mirobot_data/W10 --out data/hdf5_w10
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def export_one(args):
    ep, out, color, max_frame_ms = args
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
    import cv2
    import h5py
    cv2.setNumThreads(2)
    from docs.W9.d405.export_real_hdf5 import export_episode
    try:
        r = export_episode(Path(ep), Path(out), color, real_success=True, skip_existing=True)
    except Exception as error:  # 한 녹화가 실패해도 나머지는 계속
        return dict(episode=Path(ep).name, status="failed", error=f"{type(error).__name__}: {error}")
    with h5py.File(r["path"], "r+") as f:
        demo = f["data/demo_0"]
        demo.attrs["accepted_max_frame_ms"] = float(max_frame_ms)
        demo.attrs["accepted_max_frame_ms_note"] = (
            f"prepare --max-frame-ms {max_frame_ms:g} (docs/W10/HDF5_ALIGNMENT.md); exporter default 40 corrected "
            "by tools/build_real_dataset.py")
        follow = demo["follow_error_mm_deg"][:]
    return dict(episode=Path(ep).name, color=color, status=r["status"], steps=r["steps"], path=r["path"],
                follow_mm_mean=float(follow[:, 0].mean()), follow_mm_max=float(follow[:, 0].max()),
                follow_deg_max=float(follow[:, 1].max()))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("root", type=Path, help="녹화 폴더, 예: Mirobot_data/W10")
    p.add_argument("--out", type=Path, required=True, help="학습 데이터 폴더, 예: data/hdf5_w10")
    p.add_argument("--suite", default="mirobot_real")
    p.add_argument("--max-frame-ms", type=float, default=70.0)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--t5-source", type=Path, default=REPO / "data/hdf5_mix/t5_embeddings.pkl")
    p.add_argument("--stats-source", type=Path, default=REPO / "data/hdf5_mix/dataset_statistics.json")
    a = p.parse_args()

    from tools.inventory_recordings import inspect
    eps = sorted(d for d in a.root.iterdir() if d.is_dir() and (d / "metadata.json").exists())
    rows = [inspect(ep, a.max_frame_ms, 150.0) for ep in eps]
    ready = [r for r in rows if r["ready"]]
    print(f"녹화 {len(rows)}개 중 ready {len(ready)}개 ({dict(Counter(r['color'] for r in ready))})")
    for r in rows:
        if not r["ready"]:
            print(f"  제외 {r['episode']}: {'; '.join(r['problems'])}")

    suite = a.out / a.suite
    suite.mkdir(parents=True, exist_ok=True)
    jobs = [(str(a.root / r["episode"]), str(suite), r["color"], a.max_frame_ms) for r in ready]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        results = list(pool.map(export_one, jobs))
    status = Counter(r["status"] for r in results)
    print(f"HDF5: {dict(status)}")
    for r in results:
        if r["status"] == "failed":
            print(f"  실패 {r['episode']}: {r['error']}")
    made = {Path(r["path"]).name for r in results if r["status"] != "failed"}
    extra = sorted(f.name for f in suite.glob("*.hdf5") if f.name not in made)
    if extra:
        print(f"  주의 — ready 가 아닌데 폴더에 남은 HDF5 {len(extra)}개 (학습에 들어간다): {extra}")

    for src, name in [(a.t5_source, "t5_embeddings.pkl"), (a.stats_source, "dataset_statistics.json")]:
        if not (a.out / name).exists():
            shutil.copy2(src, a.out / name)
    from docs.W9.d405.check_dataset import check, check_embeddings
    structure = check(a.out)
    check_embeddings(a.out / "t5_embeddings.pkl", structure["instructions"])
    print(f"구조·T5 검사 통과: {structure['episodes']}개, {structure['steps']}칸, 지시문 {len(structure['instructions'])}개")

    ok = [r for r in results if r["status"] != "failed"]
    summary = dict(root=str(a.root), out=str(a.out), recordings=len(rows), ready=len(ready),
                   hdf5_status=dict(status), extra_hdf5=extra, structure=structure,
                   by_color={c: dict(episodes=sum(r["color"] == c for r in ok),
                                     steps=sum(r["steps"] for r in ok if r["color"] == c)) for c in ("red", "green", "blue")},
                   follow_mm_mean=sum(r["follow_mm_mean"] * r["steps"] for r in ok) / max(1, sum(r["steps"] for r in ok)),
                   follow_mm_max=max((r["follow_mm_max"] for r in ok), default=None),
                   excluded={r["episode"]: r["problems"] for r in rows if not r["ready"]}, episodes=results)
    (a.out / "build_summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"summary → {a.out / 'build_summary.json'}")
    print("\n남은 확인 (GPU 메모리는 안 쓴다):")
    print(f"  CUDA_VISIBLE_DEVICES='' HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 cosmos-policy/.venv/bin/python -m tools.check_cosmos_dataset "
          f"--data-dir {a.out} --statistics {a.out}/dataset_statistics.json --t5 {a.out}/t5_embeddings.pkl "
          f"--report {a.out}/loader_validation.json")
    print(f"  CUDA_VISIBLE_DEVICES=3 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 cosmos-policy/.venv/bin/python -m docs.W9.d405.train "
          f"--cosmos-repo cosmos-policy --data-dir {a.out} --checkpoint <LIBERO .pt> --gpus 2 --steps 2000 --job-name <이름> --dryrun"
          "   # 설정만 푼다. flash-attn 확인 때문에 GPU 가 보여야 한다")


if __name__ == "__main__":
    main()
