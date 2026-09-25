#!/usr/bin/env python3
from pathlib import Path

p4a_dir = Path("/root/build_wasaet/.buildozer/android/platform/python-for-android")

p3_path = p4a_dir / "pythonforandroid" / "recipes" / "python3" / "__init__.py"
if p3_path.exists():
    content = p3_path.read_text(encoding="utf-8")
    content = content.replace("version = '3.14.2'", "version = '3.11.13'")
    _ = p3_path.write_text(content, encoding="utf-8")
    print(f"Patched {p3_path} to 3.11.13")

hp3_path = p4a_dir / "pythonforandroid" / "recipes" / "hostpython3" / "__init__.py"
if hp3_path.exists():
    content = hp3_path.read_text(encoding="utf-8")
    content = content.replace('version = "3.14.2"', 'version = "3.11.13"')
    _ = hp3_path.write_text(content, encoding="utf-8")
    print(f"Patched {hp3_path} to 3.11.13")

myc_path = p4a_dir / "pythonforandroid" / "recipes" / "materialyoucolor" / "__init__.py"
if myc_path.exists():
    content = myc_path.read_text(encoding="utf-8")
    content = content.replace('version = "2.0.10"', 'version = "3.0.4"')
    _ = myc_path.write_text(content, encoding="utf-8")
    print(f"Patched {myc_path} to 3.0.4")

build_py_path = p4a_dir / "pythonforandroid" / "build.py"
if build_py_path.exists():
    b_content = build_py_path.read_text(encoding="utf-8")
    target_snippet = """    # Use our hostpython to create the virtualenv
    host_python = sh.Command(ctx.hostpython)
    with current_directory(join(ctx.build_dir)):
        shprint(host_python, '-m', 'venv', 'venv')

        # Prepare base environment and upgrade pip:
        base_env = dict(copy.copy(os.environ))
        base_env["PYTHONPATH"] = ctx.get_site_packages_dir(arch)
        info('Upgrade pip to latest version')
        shprint(sh.bash, '-c', (
            "source venv/bin/activate && pip install -U pip"
        ), _env=copy.copy(base_env))

        # Install Cython in case modules need it to build:
        info('Install Cython in case one of the modules needs it to build')
        shprint(sh.bash, '-c', (
            "venv/bin/pip install Cython"
        ), _env=copy.copy(base_env))"""

    replacement_snippet = """    # Use our hostpython to create the virtualenv
    host_python = sh.Command(ctx.hostpython)
    with current_directory(join(ctx.build_dir)):
        base_env = dict(copy.copy(os.environ))
        base_env["PYTHONPATH"] = ctx.get_site_packages_dir(arch)
        if not os.path.exists('venv'):
            shprint(host_python, '-m', 'venv', 'venv')
            info('Install Cython in case one of the modules needs it to build')
            shprint(sh.bash, '-c', (
                "venv/bin/pip install Cython"
            ), _env=copy.copy(base_env))"""

    if target_snippet in b_content:
        b_content = b_content.replace(target_snippet, replacement_snippet)
        _ = build_py_path.write_text(b_content, encoding="utf-8")
        print("Patched build.py to keep venv intact and avoid pip corruption")

# Ensure arabic_reshaper config is compatible
target_sp = Path("/root/build_wasaet/.buildozer/android/platform/build-arm64-v8a/build/python-installs/wasaetdhakiyah/arm64-v8a")
reshaper_cfg = target_sp / "arabic_reshaper" / "reshaper_config.py"
if reshaper_cfg.exists():
    cfg_text = reshaper_cfg.read_text(encoding="utf-8")
    cfg_text = cfg_text.replace("configuration: dict | None = None", "configuration = None")
    cfg_text = cfg_text.replace("configuration_file: str | None = None", "configuration_file = None")
    _ = reshaper_cfg.write_text(cfg_text, encoding="utf-8")
    print("Patched arabic_reshaper config for Python compatibility")

# Ensure pure python bidi is in target
venv_bidi = Path("/root/build_wasaet/.buildozer/android/platform/build-arm64-v8a/build/venv/lib/python3.11/site-packages/bidi")
target_bidi = target_sp / "bidi"
if venv_bidi.exists() and not (target_bidi / "algorithm.py").exists():
    import shutil
    if target_bidi.exists():
        shutil.rmtree(target_bidi)
    shutil.copytree(venv_bidi, target_bidi)
    print("Copied pure python bidi to target site-packages")

print("All recipes patched successfully!")
