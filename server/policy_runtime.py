"""W10 wrist-only Cosmos Policy inference, shared by robot runners.

Use the Cosmos virtualenv. Importing this module does not initialize CUDA or
import Cosmos; a runner can inspect its CLI and validate paths without a GPU.
The model uses the same image augmentation, statistics and T5 cache as training.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
import ast
import inspect
import os
from pathlib import Path
import pickle
import tempfile
import textwrap
import time


REPO = Path(__file__).resolve().parents[1]
W10_DATA = REPO / "cosmos-policy/W10/datasets/real/mirobot_l01_l30/processed"
W10_CHECKPOINT = (
    REPO / "cosmos-policy/W10/runs/real/cosmos_policy/w9_mirobot"
    "/w10_mirobot_l01_l30_follow_4000/checkpoints/iter_000004000"
)
EXPERIMENT = "cosmos_predict2_2b_480p_libero__inference_only"
WRIST_ONLY_OPTS = (
    "model.config.state_t=7",
    "model.config.min_num_conditional_frames=3",
    "model.config.max_num_conditional_frames=3",
    "model.config.tokenizer.chunk_duration=25",
)
CHUNK_SIZE = 16


@dataclass(frozen=True)
class PolicyConfig:
    checkpoint: Path = W10_CHECKPOINT
    statistics: Path = W10_DATA / "dataset_statistics.json"
    t5_embeddings: Path = W10_DATA / "t5_embeddings.pkl"
    cosmos_repo: Path = REPO / "cosmos-policy"
    denoising_steps: int = 5
    seed: int = 1
    capture_features: bool = True


class PolicyFeatureCapture:
    """Observe the final denoising projection input without changing model outputs.

    The wrist-only layout places the action latent at index 3. Spatial action
    tokens and pooled latent-frame features are stored separately: these are
    Cosmos features, not OpenVLA tokens or trained SAFE/Hide-and-Seek scores.
    """
    def __init__(self, model, enabled=True):
        self.handle = None
        self.tensor = None
        self.calls = 0
        self.step_means = []
        self.metadata = {"status": "disabled" if not enabled else "unsupported",
                         "source": "net.final_layer.linear input",
                         "action_latent_index": 3, "selection": "last forward call (final denoising step), all batch rows; per-step means in action_token_mean_by_step",
                         "guidance_branch": "not_inferred"}
        layer = getattr(getattr(getattr(model, "net", None), "final_layer", None), "linear", None)
        if enabled and hasattr(layer, "register_forward_pre_hook"):
            self.handle = layer.register_forward_pre_hook(self._capture)

    def _capture(self, _module, inputs):
        if inputs and hasattr(inputs[0], "detach"):
            self.tensor = inputs[0].detach()
            self.calls += 1
            # One call per denoising step; SAFE also reads non-final steps.
            if self.tensor.ndim == 5 and self.tensor.shape[1] > 3:
                self.step_means.append(self.tensor[:, 3].float().mean(dim=(1, 2)).cpu())

    def close(self):
        if self.handle is not None:
            self.handle.remove()
            self.handle = None

    def arrays(self):
        value = self.tensor
        self.tensor = None
        if value is None:
            return {}
        self.metadata.update(shape=list(value.shape), forward_calls=self.calls)
        if value.ndim != 5 or value.shape[1] <= 3:
            self.metadata["status"] = "unsupported_shape"
            return {}
        self.metadata["status"] = "captured"
        arrays = {"action_spatial_tokens": value[:, 3].float().cpu().numpy(),
                  "latent_frame_mean": value.float().mean(dim=(2, 3)).cpu().numpy()}
        if self.step_means:
            import torch
            # (denoising_steps, batch, channels): action-latent spatial mean at every step.
            arrays["action_token_mean_by_step"] = torch.stack(self.step_means).numpy()
        return arrays


@dataclass(frozen=True)
class InferenceConfig:
    """Fields consumed by the installed ``cosmos_utils.get_action``."""

    suite: str = "libero"
    use_wrist_image: bool = True
    use_third_person_image: bool = False
    num_wrist_images: int = 1
    num_third_person_images: int = 1
    use_proprio: bool = True
    normalize_proprio: bool = True
    unnormalize_actions: bool = True
    chunk_size: int = CHUNK_SIZE
    use_variance_scale: bool = False
    trained_with_image_aug: bool = True
    use_jpeg_compression: bool = False


def _absolute(path: Path) -> Path:
    # Preserve .pt symlink names: their targets in the HF cache have no suffix.
    return Path(os.path.abspath(Path(path).expanduser()))


@contextmanager
def _working_directory(directory: Path):
    """Upstream config resolves local assets relative to its repository."""
    previous = Path.cwd()
    try:
        os.chdir(directory)
        yield
    finally:
        os.chdir(previous)


def consolidate_checkpoint(checkpoint: Path) -> Path:
    """Return a .pt file, atomically converting a native iter_*/model DCP.

    A failed conversion never leaves the final cache filename behind. Existing
    consolidated files from ``tools.eval_offline`` are reused.
    """
    checkpoint = _absolute(checkpoint)
    if checkpoint.is_file():
        if checkpoint.suffix != ".pt":
            raise ValueError(f"Expected a .pt checkpoint: {checkpoint}")
        return checkpoint
    if not checkpoint.is_dir():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint}")
    source = checkpoint / "model" if (checkpoint / "model").is_dir() else checkpoint
    target = source.parent / "model_consolidated.pt"
    if not (source / ".metadata").is_file():
        raise FileNotFoundError(f"DCP metadata not found: {source / '.metadata'}")
    if target.is_file() and target.stat().st_size:
        return target

    from torch.distributed.checkpoint.format_utils import dcp_to_torch_save

    handle, name = tempfile.mkstemp(prefix=".model_consolidated_", suffix=".pt", dir=target.parent)
    os.close(handle)
    temporary = Path(name)
    started = time.perf_counter()
    try:
        dcp_to_torch_save(str(source), str(temporary))
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Consolidated checkpoint: {target} ({time.perf_counter() - started:.1f} s)")
    return target


def _load_network_state(model, state) -> int:
    """Bypass Cosmos' shape-tolerant wrapper and strictly load the policy net.

    Cosmos' model.load_state_dict(strict=False) returns None and can merely log
    incompatible tensor shapes. Its native DCP contains net.* weights only;
    loading the underlying torch module enforces both names and tensor shapes.
    """
    if not isinstance(state, dict) or not state:
        raise RuntimeError("Checkpoint must contain a nonempty net.* state dictionary")
    unexpected = [key for key in state if not isinstance(key, str) or not key.startswith("net.")]
    if unexpected:
        raise RuntimeError(f"Checkpoint contains unexpected non-network keys: {unexpected[:8]}")
    network_state = {key[len("net."):]: value for key, value in state.items()}
    try:
        model.net.load_state_dict(network_state, strict=True)
    except RuntimeError as error:
        raise RuntimeError(f"Checkpoint does not match the inference network: {error}") from error
    return len(state)


def _wrist_only_compatibility(get_action):
    """Initialize the two absent-camera indices in the installed official code.

    Upstream builds a correct wrist-only model input, but unconditionally reads
    two third-person-only locals when constructing its return metadata. Keep
    its complete inference path and add the same -1 sentinel it already uses
    for absent cameras in data_batch. Compile into a copy of its globals; this
    changes neither upstream files nor its module's global function binding.
    The narrow source checks fail explicitly if the installed API changes.
    """
    names = {"future_image_latent_idx", "future_image2_latent_idx"}
    tree = ast.parse(textwrap.dedent(inspect.getsource(get_action)))
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise RuntimeError("Unsupported Cosmos get_action source for wrist-only compatibility")
    function = tree.body[0]
    if function.name != "get_action" or not function.args.args or function.args.args[0].arg != "cfg":
        raise RuntimeError("Unsupported Cosmos get_action signature for wrist-only compatibility")
    initialized = set()
    for statement in function.body:
        if isinstance(statement, ast.Assign) and isinstance(statement.value, ast.UnaryOp):
            if isinstance(statement.value.op, ast.USub) and isinstance(statement.value.operand, ast.Constant):
                if statement.value.operand.value == 1:
                    initialized.update(target.id for target in statement.targets if isinstance(target, ast.Name))
    missing = names - initialized
    if not missing:
        return get_action
    returned = any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict"
        and names <= {
            keyword.arg for keyword in node.keywords
            if isinstance(keyword.value, ast.Name) and keyword.value.id == keyword.arg
        }
        for node in ast.walk(function)
    )
    camera_assignments = set()
    for node in ast.walk(function):
        if (
            isinstance(node, ast.If) and isinstance(node.test, ast.Attribute)
            and isinstance(node.test.value, ast.Name) and node.test.value.id == "cfg"
            and node.test.attr == "use_third_person_image"
        ):
            for statement in node.body:
                for child in ast.walk(statement):
                    if isinstance(child, ast.Assign):
                        camera_assignments.update(
                            target.id for target in child.targets if isinstance(target, ast.Name)
                        )
    if not returned or not missing <= camera_assignments or get_action.__closure__:
        raise RuntimeError("Installed Cosmos get_action differs from the supported wrist-only compatibility pattern")
    initialization = ast.Assign(
        targets=[ast.Name(id=name, ctx=ast.Store()) for name in sorted(missing)],
        value=ast.UnaryOp(op=ast.USub(), operand=ast.Constant(value=1)),
    )
    body_start = int(
        bool(function.body) and isinstance(function.body[0], ast.Expr)
        and isinstance(function.body[0].value, ast.Constant)
        and isinstance(function.body[0].value.value, str)
    )
    function.body.insert(body_start, initialization)
    namespace = dict(get_action.__globals__)
    exec(compile(ast.fix_missing_locations(tree), get_action.__code__.co_filename, "exec"), namespace)
    return namespace[function.name]


class CosmosPolicy:
    """Load the trained policy once and predict denormalized OSC action chunks.

    ``predict`` takes an already calibrated/cropped 256x256 RGB uint8 image,
    nine proprio values in training order, and an exact cached instruction.
    It returns a finite float32 array of shape (16, 7). It never sends commands
    to hardware. Construct and call this object from one thread: the upstream
    loader needs a temporary process-wide change of working directory.
    """

    def __init__(self, config: PolicyConfig | None = None):
        config = config or PolicyConfig()
        self.config = replace(
            config,
            checkpoint=_absolute(config.checkpoint),
            statistics=_absolute(config.statistics),
            t5_embeddings=_absolute(config.t5_embeddings),
            cosmos_repo=_absolute(config.cosmos_repo),
        )
        if self.config.denoising_steps <= 0:
            raise ValueError("denoising_steps must be positive")
        for path in (
            self.config.statistics,
            self.config.t5_embeddings,
            self.config.cosmos_repo / "cosmos_policy/config/config.py",
        ):
            if not path.is_file():
                raise FileNotFoundError(path)

        # All assets for this deployment are already cached on the GPU server.
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        import numpy as np
        import torch

        self._torch = torch
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is required; run with cosmos-policy/.venv/bin/python on the GPU server")
        with self.config.t5_embeddings.open("rb") as source:
            cached = pickle.load(source)
        if not isinstance(cached, dict) or not cached:
            raise ValueError("T5 cache must be a nonempty instruction-to-embedding dictionary")
        self._embeddings = {}
        for instruction, embedding in cached.items():
            if not isinstance(instruction, str):
                raise ValueError("T5 cache instruction keys must be strings")
            if hasattr(embedding, "detach"):
                embedding = embedding.detach().float().cpu().numpy()
            embedding = np.asarray(embedding, dtype=np.float32)
            if embedding.shape not in ((1, 512, 1024), (512, 1024)) or not np.isfinite(embedding).all():
                raise ValueError(f"Invalid cached T5 embedding for {instruction!r}: {embedding.shape}")
            self._embeddings[instruction] = embedding.reshape(1, 512, 1024)

        self.checkpoint = consolidate_checkpoint(self.config.checkpoint)
        self.cfg = InferenceConfig()
        self.last_inference_seconds = None
        with _working_directory(self.config.cosmos_repo):
            from cosmos_policy.experiments.robot.cosmos_utils import get_action, load_dataset_stats
            from cosmos_policy._src.predict2.utils.model_loader import load_model_from_checkpoint

            self.stats = load_dataset_stats(str(self.config.statistics))
            for key, length in (("actions_min", 7), ("actions_max", 7), ("proprio_min", 9), ("proprio_max", 9)):
                value = np.asarray(self.stats.get(key), dtype=float)
                if value.shape != (length,) or not np.isfinite(value).all():
                    raise ValueError(f"Invalid normalization statistics {key}: expected {length} finite values")
            for prefix in ("actions", "proprio"):
                if (self.stats[f"{prefix}_max"] <= self.stats[f"{prefix}_min"]).any():
                    raise ValueError(f"Normalization {prefix}_max must exceed {prefix}_min")

            model, _ = load_model_from_checkpoint(
                experiment_name=EXPERIMENT,
                s3_checkpoint_dir=str(self.checkpoint),
                config_file="cosmos_policy/config/config.py",
                load_ema_to_reg=False,
                instantiate_ema=False,
                experiment_opts=list(WRIST_ONLY_OPTS),
                skip_load_model=True,
            )
            state = torch.load(str(self.checkpoint), map_location="cpu", weights_only=False, mmap=True)
            loaded_keys = _load_network_state(model, state)
            self.load_report = {
                "checkpoint": str(self.checkpoint),
                "loaded_keys": loaded_keys,
                "missing_net_keys": [],
                "missing_non_net_keys": [],
                "unexpected_keys": [],
                "experiment": EXPERIMENT,
                "experiment_opts": list(WRIST_ONLY_OPTS),
                "compatibility": "official get_action with inactive third-person metadata indices initialized to -1",
            }
            del state
            self.model = model.eval().to("cuda")
            self._get_action = _wrist_only_compatibility(get_action)
        print(f"Loaded trained policy: {self.load_report['loaded_keys']} keys, no missing net.* or unexpected keys")

    @property
    def instructions(self) -> tuple[str, ...]:
        return tuple(sorted(self._embeddings))

    def predict(self, wrist_rgb, proprio, instruction: str):
        import numpy as np

        if instruction not in self._embeddings:
            raise ValueError(f"Instruction is absent from the training T5 cache: {instruction!r}; choose {self.instructions}")
        image = np.asarray(wrist_rgb)
        state = np.asarray(proprio, dtype=np.float32)
        if image.shape != (256, 256, 3) or image.dtype != np.uint8:
            raise ValueError("wrist_rgb must be a calibrated 256x256x3 RGB uint8 image")
        if state.shape != (9,) or not np.isfinite(state).all():
            raise ValueError("proprio must contain nine finite values in the training order")
        observation = {"wrist_image": image, "primary_image": image, "proprio": state}
        self._torch.cuda.synchronize()
        started = time.perf_counter()
        capture = PolicyFeatureCapture(self.model, enabled=self.config.capture_features)
        try:
            with _working_directory(self.config.cosmos_repo):
                output = self._get_action(
                self.cfg,
                self.model,
                self.stats,
                observation,
                self._embeddings[instruction],
                seed=self.config.seed,
                randomize_seed=False,
                num_denoising_steps_action=self.config.denoising_steps,
                generate_future_state_and_value_in_parallel=False,
                )
        finally:
            capture.close()
        self._torch.cuda.synchronize()
        self.last_inference_seconds = time.perf_counter() - started
        feature_started = time.perf_counter()
        self.last_features = capture.arrays()
        self.feature_metadata = capture.metadata
        self.feature_metadata["export_seconds"] = time.perf_counter() - feature_started
        actions = np.asarray(output["actions"], dtype=np.float32)
        if actions.shape != (CHUNK_SIZE, 7) or not np.isfinite(actions).all():
            raise RuntimeError(f"Policy returned invalid actions: expected finite ({CHUNK_SIZE}, 7), got {actions.shape}")
        return actions
