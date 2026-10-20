#!/usr/bin/env python3
"""Paso 4: consolida respuestas de los paneles en datos/*.csv y reporta CR por experto."""
import glob
import os
import sys

import numpy as np
import pandas as pd
from comun import ruta
from tdps_experimento import matriz_ahp, pesos_cr

errores = []

# ---------------- AHP ----------------
fa = sorted(glob.glob(ruta("respuestas", "ahp", "*.csv")))
if fa:
    ahp = pd.concat([pd.read_csv(f) for f in fa], ignore_index=True)
    ahp["experto"] = ahp["experto"].astype(str).str.strip()
    for e, g in ahp.groupby("experto"):
        if len(g.drop_duplicates(["i", "j"])) != 10:
            errores.append(f"AHP {e}: no tiene las 10 comparaciones unicas.")
    ahp = ahp.drop_duplicates(["experto", "i", "j"], keep="last")
    ahp.to_csv(ruta("datos", "ahp_expertos.csv"), index=False)
    print(f"AHP: {ahp['experto'].nunique()} expertos")
    for e, g in ahp.groupby("experto"):
        w, cr = pesos_cr(matriz_ahp(g))
        print(f"  {e}: CR={cr:.3f} {'OK' if cr < 0.10 else '<-- REVISAR: pida al experto revisar sus comparaciones'}")
else:
    print("AHP: no hay archivos en respuestas/ahp/")

# ---------------- Ranking ----------------
fr = sorted(glob.glob(ruta("respuestas", "ranking", "*.csv")))
if fr:
    rk = pd.concat([pd.read_csv(f) for f in fr], ignore_index=True)
    rk["evaluador"] = rk["evaluador"].astype(str).str.strip()
    bl = pd.read_csv(ruta("paneles", "bloques.csv"))
    asig = pd.read_csv(ruta("paneles", "asignacion_bloques.csv"))
    esperado = set(map(tuple, asig.values))
    filas = []
    for (e, b), g in rk.groupby(["evaluador", "bloque"]):
        ids = set(bl.loc[bl["bloque"] == b, "item_id"])
        n = len(ids)
        if (e, b) not in esperado:
            errores.append(f"Ranking {e}/{b}: el evaluador no estaba asignado a ese bloque.")
        if set(g["item_id"]) != ids or sorted(g["rank"]) != list(range(1, n + 1)):
            errores.append(f"Ranking {e}/{b}: items o rangos incompletos/duplicados.")
            continue
        g = g.copy()
        g["rank"] = g["rank"] / n          # percentil dentro del bloque (comparable entre bloques)
        filas.append(g[["evaluador", "bloque", "item_id", "rank"]])
    if filas:
        out = pd.concat(filas)
        out.to_csv(ruta("datos", "ranking_expertos.csv"), index=False)
        print(f"Ranking: {out['evaluador'].nunique()} evaluadores, {out['bloque'].nunique()} bloques, "
              f"{len(out)} filas. Faltan {len(esperado - set(map(tuple, out[['evaluador','bloque']].drop_duplicates().values)))} (evaluador,bloque).")
else:
    print("Ranking: no hay archivos en respuestas/ranking/")

# ---------------- Puntuacion V y E_sp ----------------
fp = sorted(glob.glob(ruta("respuestas", "puntuacion", "*.csv")))
if fp:
    partes = []
    for f in fp:
        d = pd.read_csv(f)
        d["evaluador"] = os.path.splitext(os.path.basename(f))[0]
        partes.append(d[["item_id", "V", "E_sp", "evaluador"]])
    pt = pd.concat(partes)
    if not pt["V"].dropna().between(1, 5).all():
        errores.append("Puntuacion: V debe estar entre 1 y 5.")
    if not pt["E_sp"].dropna().isin([1, 2, 3, 5, 8, 13, 21]).all():
        errores.append("Puntuacion: E_sp debe ser 1,2,3,5,8,13 o 21.")
    nr = pt.dropna(subset=["V", "E_sp"]).groupby("item_id").size()
    agg = pt.groupby("item_id")[["V", "E_sp"]].median()
    items = pd.read_csv(ruta("datos", "items.csv"))
    items["V"] = items["item_id"].map(agg["V"])
    items["E_sp"] = items["item_id"].map(agg["E_sp"])
    items.to_csv(ruta("datos", "items.csv"), index=False)
    print(f"Puntuacion: {pt['evaluador'].nunique()} puntuadores; mediana por item. "
          f"Items con <2 puntuadores: {int((nr.reindex(items['item_id']).fillna(0) < 2).sum())}")
    wide = pt.pivot_table(index="item_id", columns="evaluador", values="V")
    if wide.shape[1] >= 2:
        print(f"  Acuerdo en V (correlacion de Spearman media entre puntuadores): "
              f"{np.nanmean(wide.corr(method='spearman').values[np.triu_indices(wide.shape[1], 1)]):.2f}")
else:
    print("Puntuacion: no hay archivos en respuestas/puntuacion/")

if errores:
    print("\nERRORES:")
    [print(" -", e) for e in errores]
    sys.exit(1)
print("\nSIGUIENTE: python scripts/05_validar_datos.py")
