"""Hot-sync updated python and kv files directly to the connected Android device via ADB

without needing to rebuild or redownload the APK.
"""

import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

PACKAGE = "com.cosmosort.ai.cosmosort"
ACTIVITY = f"{PACKAGE}/org.kivy.android.PythonActivity"
WORKSPACE = Path(__file__).resolve().parent.parent


def run_cmd(cmd: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run shell command synchronously and print output."""
    print(f"RUN: {cmd}")
    res = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=WORKSPACE,
        check=False,
    )
    if res.stdout:
        print(res.stdout.strip())
    if res.stderr and res.returncode != 0:
        print(f"ERROR: {res.stderr.strip()}")
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed with code {res.returncode}: {cmd}")
    return res


def collect_files() -> list[Path]:
    """Collect source files eligible for hot-sync."""
    files_to_sync: list[Path] = []

    # Root python files
    for f in sorted(WORKSPACE.glob("*.py")):
        if f.name.startswith("test_") or f.name == "conftest.py":
            continue
        files_to_sync.append(f)

    # KV files
    kv_dir = WORKSPACE / "kv"
    if kv_dir.exists():
        files_to_sync.extend(sorted(kv_dir.glob("*.kv")))

    # Screens
    screens_dir = WORKSPACE / "screens"
    if screens_dir.exists():
        files_to_sync.extend(sorted(screens_dir.glob("*.py")))

    # Utils
    utils_dir = WORKSPACE / "utils"
    if utils_dir.exists():
        files_to_sync.extend(sorted(utils_dir.glob("*.py")))

    return files_to_sync


def main() -> None:
    """Execute hot-sync of project files to device."""
    print("=== Rateb Hot-Sync to Connected Device ===")

    # Verify adb device
    res = run_cmd("adb devices", check=True)
    if "device" not in res.stdout.replace("List of devices attached", ""):
        print("No connected device detected!")
        sys.exit(1)

    files = collect_files()
    print(f"Found {len(files)} files to sync:")
    for f in files:
        rel = f.relative_to(WORKSPACE)
        print(f"  - {rel}")

    # Create tar archive
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        tar_path = tmp_path / "app_update.tar"
        with tarfile.open(tar_path, "w") as tar:
            for f in files:
                rel = f.relative_to(WORKSPACE)
                tar.add(f, arcname=str(rel).replace("\\", "/"))

        print(f"\nCreated bundle ({tar_path.stat().st_size} bytes)")

        # Push tar to device
        print("Pushing bundle to device...")
        run_cmd(f'adb push "{tar_path}" /data/local/tmp/app_update.tar')

        # Create sync script locally in tempdir
        sync_app_script = """
APP_DIR=/data/data/com.cosmosort.ai.cosmosort/files/app
SRC_DIR=/data/local/tmp/app_sync

echo "Copying files to $APP_DIR..."
cp -r $SRC_DIR/* $APP_DIR/

echo "Removing stale pyc and pycache..."
rm -f $APP_DIR/*.pyc
rm -f $APP_DIR/screens/*.pyc
rm -f $APP_DIR/utils/*.pyc
rm -rf $APP_DIR/__pycache__
rm -rf $APP_DIR/screens/__pycache__
rm -rf $APP_DIR/utils/__pycache__

echo "Ensuring permissions..."
chmod -R 700 $APP_DIR

echo "HOT SYNC DONE"
"""
        local_sync_sh = tmp_path / "device_sync.sh"
        with open(local_sync_sh, "w", newline="\n") as f_sh:
            f_sh.write(sync_app_script)

        run_cmd(f'adb push "{local_sync_sh}" /data/local/tmp/device_sync.sh')

    # Setup commands on device
    sh_script = (
        "rm -rf /data/local/tmp/app_sync && "
        "mkdir -p /data/local/tmp/app_sync && "
        "tar --no-same-owner -xf /data/local/tmp/app_update.tar -C /data/local/tmp/app_sync && "
        "chmod -R 777 /data/local/tmp/app_sync"
    )
    run_cmd(f'adb shell "{sh_script}"')

    run_cmd('adb shell "chmod 777 /data/local/tmp/device_sync.sh"')

    print("\nApplying update inside app container...")
    res = run_cmd(
        f'adb shell "run-as {PACKAGE} /system/bin/sh /data/local/tmp/device_sync.sh"'
    )
    print(res.stdout)

    # Clean temporary files on device
    run_cmd(
        'adb shell "rm -f /data/local/tmp/app_update.tar /data/local/tmp/device_sync.sh"'
    )

    print("\nRestarting app...")
    run_cmd(f"adb shell am force-stop {PACKAGE}")
    run_cmd("adb logcat -c")
    run_cmd(f"adb shell am start -n {ACTIVITY}")

    print("\nApp started! Monitoring logcat for 5 seconds...")
    time.sleep(5)

    log_res = run_cmd("adb logcat -d -s python:V")
    print("\n--- Recent Python Logcat ---")
    lines = log_res.stdout.splitlines()[-40:]
    for line in lines:
        print(line)


if __name__ == "__main__":
    main()
