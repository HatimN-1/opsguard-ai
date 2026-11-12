"""Restore the missing numeric-counter rule in Qwen grounding V3.

Only one exact source string is changed; no logs, docs or guard code are touched.
"""

import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "app" / "adf_monitor" / "enterprise_agent.py"
EXPECTED_V3_SHA256 = "f53a08e599f6edd2d0fdae0a251a46b53871b359490430dfa007990b7e9f36b4"
OLD_RULE = "Ne cite aucun compteur de lignes, événements, échecs ou exécutions. "
# Replacement keeps the Python source wrapped in two adjacent string literals.
NEW_RULE = (
    "N'utilise AUCUN nombre de lignes, d'événements, de succès, d'échecs, \""
    "\n        \"d'étapes ou d'exécutions : les compteurs sont calculés séparément. "
)


def main() -> None:
    if not TARGET.is_file():
        raise SystemExit(f"Fichier manquant : {TARGET}")
    original = TARGET.read_bytes()
    text = original.decode("utf-8")
    if NEW_RULE in text and OLD_RULE not in text:
        print("DEJA CORRIGE : règle numérique déjà présente ; rien à modifier.")
        return
    actual = hashlib.sha256(original).hexdigest()
    if actual != EXPECTED_V3_SHA256:
        raise SystemExit(
            "VERSION DIFFERENTE : enterprise_agent.py ne correspond pas à Qwen V3. "
            "Aucune modification. Envoie le fichier actuel pour adapter le correctif."
        )
    if text.count(OLD_RULE) != 1:
        raise SystemExit("Règle originale absente ou ambiguë ; aucune modification.")
    updated = text.replace(OLD_RULE, NEW_RULE)
    compile(updated, str(TARGET), "exec")
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    backup = PROJECT_ROOT / "outputs" / "backups" / f"enterprise_agent_qwen_v3_before_prompt_fix_{timestamp}.py"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET, backup)
    try:
        tmp = TARGET.with_suffix(".py.v3_1_tmp")
        tmp.write_text(updated, encoding="utf-8", newline="")
        tmp.replace(TARGET)
    except Exception:
        shutil.copy2(backup, TARGET)
        raise
    print("CORRECTION APPLIQUEE : consigne numérique 'AUCUN nombre' restaurée.")
    print("Prompt seulement : garde-fou, essais Qwen, documents et traces inchangés.")
    print(f"Sauvegarde : {backup}")


if __name__ == "__main__":
    main()
