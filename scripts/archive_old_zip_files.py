"""Safely move root-level installation ZIPs out of the OpsGuard repository.

By default, ONLY preview planned moves. --apply moves files to an archive folder
in the parent directory; files are not deleted or overwritten. No recursive scan.
"""

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = ROOT.parent / "OpsGuard_archives_installation"


def select_archives(root: Path, *, include_bak: bool = False) -> list[Path]:
    """Find only known obsolete installer/backup file types at the repository root."""
    suffixes = {".zip", ".bak"} if include_bak else {".zip"}
    return sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in suffixes)


def archive_files(root: Path, archive: Path, *, apply: bool,
                  include_bak: bool = False) -> list[tuple[str, str]]:
    """Return planned/performed moves; never overwrite an existing file."""
    root = root.resolve()
    archive = archive.resolve()
    if archive == root or root in archive.parents:
        raise ValueError("Archive must be outside project directory")
    actions = []
    for source in select_archives(root, include_bak=include_bak):
        destination = archive / source.name
        if destination.exists():
            actions.append((source.name, "SKIPPED_EXISTS"))
            continue
        if apply:
            archive.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
        actions.append((source.name, "MOVED" if apply else "WOULD_MOVE"))
    return actions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Execute moves (default: preview only)")
    parser.add_argument("--include-bak", action="store_true", help="Also archive .bak root files")
    args = parser.parse_args()
    actions = archive_files(ROOT, ARCHIVE_ROOT, apply=args.apply,
                            include_bak=args.include_bak)
    print("OpsGuard AI — Archivage sécurisé des ZIP d'installation")
    print(f"Dossier cible : {ARCHIVE_ROOT}")
    if not actions:
        print("Aucun ZIP à déplacer à la racine du projet.")
    for name, action in actions:
        print(f"  {action:14} {name}")
    print("Aucun fichier Python, données, tests ou environnement virtuel touché.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
