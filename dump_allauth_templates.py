import allauth
import pathlib

base = pathlib.Path(allauth.__file__).parent / "templates"

targets = [
    "socialaccount/login.html",
    "socialaccount/base.html",
    "socialaccount/base_entrance.html",
    "allauth/layouts/base.html",
    "allauth/layouts/entrance.html",
]

for rel in targets:
    p = base / rel
    print("=" * 80)
    print(rel, "  (exists)" if p.exists() else "  (MISSING)")
    print("=" * 80)
    if p.exists():
        print(p.read_text())
    print()