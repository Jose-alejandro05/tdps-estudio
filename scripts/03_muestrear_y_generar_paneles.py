#!/usr/bin/env python3
"""Paso 3: muestrea items, genera hojas de puntuacion (V, E_sp), bloques de ranking y formularios HTML."""
import json
import math
import os
import sys

import numpy as np
import pandas as pd
from comun import cfg, ruta

c = cfg()
rng = np.random.default_rng(c["semilla"])
dest_items = ruta("datos", "items.csv")
if os.path.exists(dest_items) and "--forzar" not in sys.argv:
    sys.exit("datos/items.csv ya existe. Use --forzar para regenerar (se perderan V y E_sp ya consolidados).")

REQ = ["churn", "change_freq", "issue_density", "complexity", "coupling", "coverage", "P_hours", "sonar_severity"]
commits = pd.read_csv(ruta("datos", "repos_commits.csv")).set_index("repo")
muestras = []
for r in c["repos"]:
    df = pd.read_csv(ruta("datos", "archivos", f"{r['nombre']}.csv"))
    elig = df.dropna(subset=REQ)
    elig = elig[elig["P_hours"] > 0]            # solo archivos con deuda SQALE medible
    k = c["items_por_repo"]
    if len(elig) < k:
        print(f"AVISO {r['nombre']}: solo {len(elig)} archivos elegibles (<{k}). Revise Sonar/cobertura.")
        k = len(elig)
    idx = rng.choice(len(elig), k, replace=False)
    m = elig.iloc[sorted(idx)].copy()
    m.insert(0, "item_id", [f"{r['nombre']}-{i+1:03d}" for i in range(len(m))])
    muestras.append(m)
items = pd.concat(muestras, ignore_index=True)
items["V"] = np.nan
items["E_sp"] = np.nan
cols = ["item_id", "repo", "path", "churn", "change_freq", "issue_density", "complexity", "coupling",
        "coverage", "V", "P_hours", "E_sp", "sonar_severity", "future_defects", "future_changes"]
items[cols].to_csv(dest_items, index=False)
print(f"{len(items)} items en datos/items.csv ({items['repo'].nunique()} repos)")

# --- Hoja de puntuacion CIEGA (sin metricas ni resultados futuros) ---
os.makedirs(ruta("paneles"), exist_ok=True)
items[["item_id", "repo", "path"]].assign(V="", E_sp="").to_csv(ruta("paneles", "items_para_puntuar.csv"), index=False)

# --- Bloques de ranking y asignacion de evaluadores ---
bloques, filas_b = [], []
for repo, g in items.groupby("repo"):
    ids = g["item_id"].tolist()
    rng.shuffle(ids)
    for k, parte in enumerate(np.array_split(ids, math.ceil(len(ids) / c["bloque_tamano"])), 1):
        bid = f"{repo}-B{k}"
        bloques.append((bid, list(parte)))
        filas_b += [{"bloque": bid, "item_id": i, "repo": repo} for i in parte]
pd.DataFrame(filas_b).merge(items[["item_id", "path"]], on="item_id").to_csv(ruta("paneles", "bloques.csv"), index=False)

n_ev, k_ev = c["n_evaluadores"], c["evaluadores_por_bloque"]
if k_ev > n_ev or k_ev < 3:
    sys.exit("Config: 3 <= evaluadores_por_bloque <= n_evaluadores.")
ev_ids = [f"X{i+1:02d}" for i in range(n_ev)]
asig = [{"evaluador": ev_ids[(bi * k_ev + j) % n_ev], "bloque": bid}
        for bi, (bid, _) in enumerate(bloques) for j in range(k_ev)]
asig = pd.DataFrame(asig)
asig.to_csv(ruta("paneles", "asignacion_bloques.csv"), index=False)
print(f"{len(bloques)} bloques; {asig.groupby('evaluador').size().min()}-{asig.groupby('evaluador').size().max()} bloques por evaluador")

# --- Formularios HTML de ranking ---
HTML = open(ruta("scripts", "plantilla_ranking.html"), encoding="utf-8").read()
os.makedirs(ruta("formularios"), exist_ok=True)
ix = items.set_index("item_id")
for bid, ids in bloques:
    repo = ix.loc[ids[0], "repo"]
    url = commits.loc[repo, "url"].removesuffix(".git")
    h0 = commits.loc[repo, "commit_t0"]
    lista = []
    for i in ids:
        p = ix.loc[i, "path"]
        link = f"{url}/blob/{h0}/{p}" if "github.com" in url else ""
        lista.append({"item_id": i, "path": p, "link": link})
    out = (HTML.replace("__BLOQUE__", bid).replace("__REPO__", repo)
               .replace("__ITEMS__", json.dumps(lista, ensure_ascii=False)))
    with open(ruta("formularios", f"ranking_{bid}.html"), "w", encoding="utf-8") as f:
        f.write(out)
print(f"{len(bloques)} formularios en formularios/ + formulario_ahp.html")
print("\nENVIE: formularios/formulario_ahp.html al panel AHP; paneles/items_para_puntuar.csv a 2-3 puntuadores;")
print("       cada evaluador de paneles/asignacion_bloques.csv recibe SOLO sus ranking_<bloque>.html.")
print("RECOJA respuestas en respuestas/{ahp,puntuacion,ranking}/ y ejecute scripts/04_consolidar_respuestas.py")
