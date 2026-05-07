#!/usr/bin/env python3
"""Bundle all 11 skill directories into a self-contained deliverable (¥499 all-inclusive)."""
import argparse, json, shutil, sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]  # aki-skills/

def bundle(target: Path):
    manifest = json.loads((SCRIPT_DIR.parent / "skill_manifest.json").read_text())
    skills = list(dict.fromkeys(
        manifest["skills"]["core"]["items"] + manifest["skills"]["full"]["items"]
    ))  # merge + dedupe all 11 skills

    target.mkdir(parents=True, exist_ok=True)
    skills_dir = target / "skills"
    skills_dir.mkdir(exist_ok=True)
    shared_dir = target / "shared"
    shared_dir.mkdir(exist_ok=True)

    src_shared = REPO_ROOT / "shared"
    if src_shared.exists():
        shutil.copytree(src_shared, shared_dir, dirs_exist_ok=True)

    for skill_name in skills:
        src = REPO_ROOT / "skills" / skill_name
        if not src.exists():
            print(f"  [WARN] Skill not found: {skill_name}")
            continue
        shutil.copytree(src, skills_dir / skill_name, dirs_exist_ok=True)
        print(f"  [OK] {skill_name}")

    shutil.copytree(SCRIPT_DIR.parent, skills_dir / "aki-content-pipeline-pro", dirs_exist_ok=True)
    shutil.copy(SCRIPT_DIR.parent / "config" / "keys.env.example", target / "keys.env.example")
    for doc in ["AGENTS.md", "README.md", "SETUP.md"]:
        p = SCRIPT_DIR.parent / doc
        if p.exists():
            shutil.copy(p, target / doc)

    print(f"\nBundle created: {target.resolve()}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="./aki-pipeline-bundle")
    args = parser.parse_args()
    bundle(Path(args.target))
