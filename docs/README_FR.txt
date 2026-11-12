OpsGuard AI - controle de traces nouvellement generees

Depuis la racine de opsguard-ai :

1. python .\scripts\verify_fresh_trace_readonly.py --mark
2. Dans Streamlit, lancer UNE investigation qui appelle un outil (ex. inspection d'un Run ID connu).
3. python .\scripts\verify_fresh_trace_readonly.py --check

Ne pas lancer d'evaluation entre les etapes 1 et 3 si vous voulez isoler
l'investigation UI. Le script n'affiche aucun prompt, aucune reponse, aucun
Run ID, aucun argument d'outil. Il ne modifie aucun journal.

Code retour : 0 PASS, 1 FAIL, 2 INCONCLUSIF/ERREUR.

ATTENTION : Le controle des anciennes traces historiques est distinct du
controle du code actuel. Il ne faut pas fabriquer des durees historiques.
