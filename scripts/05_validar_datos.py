#!/usr/bin/env python3
"""Paso 5: verificacion previa al analisis. Debe terminar sin ERRORES."""
import os
import sys

import pandas as pd
from comun import ruta

E, W = [], []
REQ = ["item_id", "repo", "churn", "change_freq", "issue_density", "complexity", "coupling", "coverage",
       "V", "P_hours", "E_sp", "sonar_severity", "future_defects", "future_changes"]
for f in ["items.csv", "ahp_expertos.csv", "ranking_expertos.csv"]:
    if not os.path.exists(ruta("datos", f)):
        E.append(f"Falta datos/{f}")
if E:
    print("\n".join("ERROR: " + e for e in E)); sys.exit(1)

it = pd.read_csv(ruta("datos", "items.csv"))
ahp = pd.read_csv(ruta("datos", "ahp_expertos.csv"))
rk = pd.read_csv(ruta("datos", "ranking_expertos.csv"))

falt = [c for c in REQ if c not in it.columns]
if falt:
    E.append(f"items.csv: faltan columnas {falt}")
else:
    na = it[REQ].isna().sum()
    if na.any():
        E.append(f"items.csv: celdas vacias -> {na[na > 0].to_dict()}")
    if it["item_id"].duplicated().any():
        E.append("items.csv: item_id duplicados")
    if not it["V"].dropna().between(1, 5).all():
        E.append("V fuera de 1-5")
    if (it["P_hours"] <= 0).any():
        E.append("P_hours debe ser > 0")
    if (it[["churn", "change_freq", "issue_density", "future_defects", "future_changes"]] < 0).any().any():
        E.append("Hay conteos negativos")
    if it["future_defects"].sum() == 0:
        E.append("future_defects suma 0: no hay criterio externo")
    elif (it["future_defects"] > 0).mean() < 0.15:
        W.append("Menos del 15% de items con defectos futuros: el criterio externo sera ruidoso.")
    if (it["future_changes"] == it["churn"]).mean() > 0.5:
        E.append("future_changes igual a churn en >50% de items: posible FUGA de informacion (ventanas solapadas).")
    if it["repo"].nunique() < 8:
        W.append(f"Solo {it['repo'].nunique()} repos: Wilcoxon por repo no alcanza p<0.05 con <6; recomendado >=8.")
    if len(it) < 64:
        W.append(f"{len(it)} items (<64): la potencia para detectar rho=0.70 vs 0.50 sera menor a 80%.")

exp, ev = set(ahp["experto"].astype(str)), set(rk["evaluador"].astype(str))
if exp & ev:
    E.append(f"Los paneles NO son independientes; codigos repetidos: {sorted(exp & ev)}")
if len(exp) < 12:
    W.append(f"{len(exp)} expertos AHP (<12).")
if len(ev) < 10:
    W.append(f"{len(ev)} evaluadores de validacion (<10).")
if not set(rk["item_id"]) <= set(it["item_id"]):
    E.append("ranking_expertos.csv contiene item_id que no estan en items.csv")
if len(ahp.groupby("experto")) and (ahp.groupby("experto").size() != 10).any():
    E.append("Algun experto AHP no tiene 10 comparaciones")
cob = rk.groupby("item_id")["evaluador"].nunique()
if cob.reindex(it["item_id"]).fillna(0).min() < 3:
    W.append("Hay items evaluados por menos de 3 evaluadores.")

for w in W:
    print("AVISO:", w)
for e in E:
    print("ERROR:", e)
if E:
    sys.exit(1)
print("\nDatos validos. Ejecute:  python tdps_experimento.py --data datos --out resultados")
