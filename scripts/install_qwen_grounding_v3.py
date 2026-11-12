"""Install Qwen3 evidence-grounding V3 on the matching source revision only.

No historical logs, catalog, credentials, evaluation labels or guard rules change.
"""

import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    ("app/adf_monitor/enterprise_agent.py", "981d184152177f372cbc0afee26eae0ee0fbcba9f5db1da1390d9cc93e35794b"),
    ("app/adf_monitor/llm_evaluation.py", "100079c06bad05c2e0687a0f3d9d44da6e7d2053563c2fe13f6b5bfcf22c10b5"),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    source_dir = ROOT / "patches" / "qwen_grounding_v3"
    pending = []
    for relative, expected in FILES:
        target = ROOT / relative
        update = source_dir / Path(relative).name
        if not target.is_file() or not update.is_file():
            raise SystemExit(f"Fichier requis introuvable : {relative}")
        current = sha256(target)
        if current == sha256(update):
            print(f"DEJA APPLIQUE : {relative}")
            continue
        if current != expected:
            raise SystemExit(
                f"VERSION DIFFERENTE : {relative}. Aucune modification effectuee. "
                "Envoyer le code actuel pour un correctif adapte."
            )
        pending.append((target, update, relative))
    if not pending:
        print("Correctif deja installe; aucune modification.")
        return
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = ROOT / "outputs" / "backups" / f"qwen_grounding_v3_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    for target, _update, relative in pending:
        saved = backup_dir / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, saved)
    try:
        for target, update, _relative in pending:
            temp_target = target.with_name(target.name + ".v3-new")
            shutil.copy2(update, temp_target)
            temp_target.replace(target)
    except Exception:
        for target, _update, relative in pending:
            shutil.copy2(backup_dir / relative, target)
        raise
    print("PATCH APPLIQUE : contexte documentaire explicite + 1 reprise controlee.")
    print("GARDE-FOU INCHANGE. Aucun journal historique modifie.")
    print(f"SAUVEGARDE : {backup_dir}")


if __name__ == "__main__":
    main()
