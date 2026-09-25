#!/usr/bin/env python3
from pathlib import Path

p4a_dir = Path("/root/build_wasaet/.buildozer/android/platform/python-for-android")

p3_path = p4a_dir / "pythonforandroid" / "recipes" / "python3" / "__init__.py"
if p3_path.exists():
    content = p3_path.read_text(encoding="utf-8")
    content = content.replace("version = '3.14.2'", "version = '3.11.13'")
    p3_path.write_text(content, encoding="utf-8")
    print(f"Patched {p3_path}")

hp3_path = p4a_dir / "pythonforandroid" / "recipes" / "hostpython3" / "__init__.py"
if hp3_path.exists():
    content = hp3_path.read_text(encoding="utf-8")
    content = content.replace('version = "3.14.2"', 'version = "3.11.13"')
    hp3_path.write_text(content, encoding="utf-8")
    print(f"Patched {hp3_path}")

print("Python 3.11.13 set successfully in recipes!")
