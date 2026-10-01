"""Check the local Windows LIBERO setup without constructing a simulator."""

import importlib
from importlib import metadata
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
if os.name == "nt":
    os.environ["MUJOCO_GL"] = "wgl"
os.environ["NUMBA_DISABLE_JIT"] = "1"

PACKAGES = (
    ("libero", "libero"),
    ("robosuite", "robosuite"),
    ("robomimic", "robomimic"),
    ("bddl", "bddl"),
    ("mujoco", "mujoco"),
    ("opencv-python", "cv2"),
    ("scipy", "scipy"),
)
SCRIPTS = (
    "test_panda_initial_pose.py", "test_libero_tabletop.py",
    "test_custom_bddl.py", "test_panda_drawer_info.py", "test_panda_drawer_action.py",
    "test_custom_task_variants.py", "test_extended_custom_tasks.py",
    "test_custom_predicate_conditions.py", "test_tabletop_configuration.py",
    "test_milk_source_scene.py", "export_custom_task_media.py",
)
CUSTOM_BDDL = (
    "custom_tasks/custom_goal_change.bddl", "custom_tasks/custom_milk_task.bddl",
    "custom_tasks/custom_new_object_task.bddl", "custom_tasks/custom_new_fixture_task.bddl",
    "custom_tasks/custom_new_predicate_task.bddl", "custom_tasks/custom_camera_control_task.bddl",
)
EXTENSIONS = (
    "libero/libero/envs/objects/custom_validation_objects.py",
    "libero/libero/envs/objects/custom_validation_fixtures.py",
    "libero/libero/envs/predicates/custom_validation_predicates.py",
    "libero/libero/envs/problems/libero_custom_support.py",
    "libero/libero/envs/problems/libero_custom_camera_control.py",
)
ASSETS = (
    "libero/libero/assets/custom_validation_objects/marker_box.xml",
    "libero/libero/assets/custom_validation_objects/raised_support.xml",
)


def main():
    print("Python executable:", sys.executable, flush=True)
    print("Python version:", sys.version.split()[0], flush=True)
    print("LIBERO root:", ROOT, flush=True)
    print("MUJOCO_GL:", os.environ.get("MUJOCO_GL", "unset"), flush=True)
    print("NUMBA_DISABLE_JIT:", os.environ["NUMBA_DISABLE_JIT"], flush=True)
    if sys.version_info[:2] != (3, 8):
        expected = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "anaconda3" / "envs" / "libero" / "python.exe"
        raise RuntimeError(
            "This recording setup uses Python 3.8. Run the checker with the libero interpreter:\n"
            '& "{}" "{}"'.format(expected, ROOT / "check_libero_setup.py")
        )

    try:
        import ssl
    except ImportError as error:
        raise RuntimeError("SSL DLL import failed. Add this environment's Library\\bin to PATH "
                           "using the chapter 5.1 setup block.") from error
    print("SSL OK:", ssl.OPENSSL_VERSION, flush=True)

    missing = [name for name in SCRIPTS + ("custom_tasks/custom_test.bddl",) +
               CUSTOM_BDDL + EXTENSIONS + ASSETS if not (ROOT / name).is_file()]
    if missing:
        raise RuntimeError("Required validation files are missing. Restore the task bundle to this LIBERO root:\n"
                           + "\n".join(missing))
    print("Files OK: {} scripts, drawer BDDL + {} A-F BDDL, {} extension modules, {} XML assets".format(
        len(SCRIPTS), len(CUSTOM_BDDL), len(EXTENSIONS), len(ASSETS)), flush=True)

    installed = {}
    for package, _ in PACKAGES:
        try:
            distribution = metadata.distribution(package)
        except metadata.PackageNotFoundError:
            raise RuntimeError("Package '{}' is not installed in {}. Check the selected libero interpreter."
                               .format(package, sys.executable))
        installed[package] = distribution.version
        print("Package {}: version={} | location={}".format(
            package, distribution.version, distribution.locate_file("")), flush=True)
    if installed["mujoco"] != "2.3.7":
        raise RuntimeError("The recorded Windows setup uses mujoco 2.3.7; this interpreter has {}. "
                           "Use the same environment before reproducing the results.".format(installed["mujoco"]))
    if installed["robosuite"].split(".")[:2] != ["1", "4"]:
        raise RuntimeError("These scripts use the robosuite 1.4 API; this interpreter has {}. "
                           "Use the recorded libero environment.".format(installed["robosuite"]))

    # Import the existing helper first so robosuite's /tmp log path is corrected on Windows.
    # Its main() is guarded, so importing it does not create a simulator or renderer.
    import test_custom_bddl  # noqa: F401
    for _, module_name in PACKAGES:
        try:
            module = importlib.import_module(module_name)
        except Exception as error:
            raise RuntimeError("Import failed for '{}': {}. Check this interpreter's dependencies and Windows rendering setup."
                               .format(module_name, error)) from error
        module_path = getattr(module, "__file__", None) or list(getattr(module, "__path__", []))
        print("Import OK: {} | path={}".format(module_name, module_path), flush=True)
    print("LIBERO setup OK", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("LIBERO setup FAILED: {}".format(error), file=sys.stderr, flush=True)
        sys.exit(1)
