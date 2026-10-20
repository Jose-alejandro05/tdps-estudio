#!/usr/bin/env python3
"""Paso 2: metricas por archivo. Predictores SOLO hasta t0; resultados SOLO t0 -> t1."""
import os
import re
import subprocess

import numpy as np
import pandas as pd
from comun import cfg, fin_dia, git, inicio_dia_siguiente, ruta

c = cfg()
T0, T1 = c["t0"], c["t1"]
RX_JAVA = re.compile(r"^\s*import\s+(?:static\s+)?([\w.*]+)\s*;", re.M)
RX_TS = re.compile(r"""(?:from\s+|require\(\s*|import\s*\(\s*)['"]([^'"]+)['"]""")
PESO = {"INFO": 1, "MINOR": 2, "MAJOR": 3, "CRITICAL": 4, "BLOCKER": 5}


def archivos(repo, commit):
    out = git(repo, "ls-tree", "-r", "--name-only", commit).splitlines()
    ex = tuple(e.lower() for e in c["extensiones"])
    return [f for f in out if f.lower().endswith(ex) and not any(x in ("/" + f).lower() for x in c["excluir_rutas"])]


def conteos(repo, rev, since, until, grep=None):
    cmd = ["log", rev, "--numstat", "--no-renames", "--pretty=format:@@%H", f"--since={since}", f"--until={until}"]
    if grep:
        cmd += ["-i", "-E", f"--grep={grep}"]
    churn, freq = {}, {}
    for line in git(repo, *cmd).splitlines():
        if line.startswith("@@"):
            continue
        p = line.split("\t")
        if len(p) == 3:
            a = int(p[0]) if p[0].isdigit() else 0
            b = int(p[1]) if p[1].isdigit() else 0
            churn[p[2]] = churn.get(p[2], 0) + a + b
            freq[p[2]] = freq.get(p[2], 0) + 1
    return churn, freq


def n_imports(repo, commit, path):
    try:
        src = subprocess.run(["git", "-C", repo, "show", f"{commit}:{path}"], capture_output=True,
                             text=True, errors="replace", check=True).stdout
    except subprocess.CalledProcessError:
        return np.nan
    return len(set(RX_JAVA.findall(src)) | set(RX_TS.findall(src)))


def sonar_get(endpoint, params, token):
    import requests
    r = requests.get(c["sonar"]["url"] + endpoint, params=params, auth=(token, ""), timeout=120)
    r.raise_for_status()
    return r.json()


def sonar_api(key, token):
    filas, p = [], 1
    while True:
        j = sonar_get("/api/measures/component_tree",
                      {"component": key, "metricKeys": "sqale_index,complexity,coverage,ncloc",
                       "qualifiers": "FIL", "ps": 500, "p": p}, token)
        for comp in j["components"]:
            d = {"path": comp["path"]}
            d.update({m["metric"]: float(m["value"]) for m in comp["measures"] if "value" in m})
            filas.append(d)
        if p * 500 >= j["paging"]["total"]:
            break
        p += 1
    med = pd.DataFrame(filas)
    mx, p = {}, 1
    while True:
        j = sonar_get("/api/issues/search", {"componentKeys": key, "resolved": "false",
                                             "types": "CODE_SMELL", "ps": 500, "p": p}, token)
        for i in j["issues"]:
            path = i["component"].split(":", 1)[1]
            mx[path] = max(mx.get(path, 0), PESO.get(i["severity"], 0))
        if p * 500 >= min(j["paging"]["total"], 10000):
            break
        p += 1
    med["sonar_severity"] = med["path"].map(mx).fillna(0)
    return med.rename(columns={"sqale_index": "sqale_min"})


os.makedirs(ruta("datos", "archivos"), exist_ok=True)
token = os.environ.get(c["sonar"]["token_env"])
commits = pd.read_csv(ruta("datos", "repos_commits.csv")).set_index("repo")
since_pre = (pd.Timestamp(T0) - pd.DateOffset(months=c["ventana_historial_meses"])).strftime("%Y-%m-%d") + " 00:00:00"

for r in c["repos"]:
    n, repo = r["nombre"], ruta("repos", r["nombre"])
    h0 = commits.loc[n, "commit_t0"]
    print(f"\n== {n} ==")
    df = pd.DataFrame({"path": archivos(repo, h0)})
    ref = git(repo, "symbolic-ref", "refs/remotes/origin/HEAD").strip()   # rama por defecto (incluye futuro)
    ch, fr = conteos(repo, h0, since_pre, fin_dia(T0))                    # PREDICTORES: ancestros de t0, <= t0
    _, iss = conteos(repo, h0, since_pre, fin_dia(T0), grep=c["regex_issue_ref"])
    fch, ffr = conteos(repo, ref, inicio_dia_siguiente(T0), fin_dia(T1))  # RESULTADOS: t0 < fecha <= t1
    _, fdef = conteos(repo, ref, inicio_dia_siguiente(T0), fin_dia(T1), grep=c["regex_defectos"])
    df["churn"] = df["path"].map(ch).fillna(0)
    df["change_freq"] = df["path"].map(fr).fillna(0)
    df["issue_density"] = df["path"].map(iss).fillna(0)
    df["coupling"] = [n_imports(repo, h0, p) for p in df["path"]]
    df["future_changes"] = df["path"].map(ffr).fillna(0)
    df["future_defects"] = df["path"].map(fdef).fillna(0)

    manual = ruta("datos", "sonar_manual", f"{n}.csv")
    if token:
        print("  SonarQube via API ...")
        sq = sonar_api(r["sonar_key"], token)
    elif os.path.exists(manual):
        print(f"  SonarQube desde {manual}")
        sq = pd.read_csv(manual)       # columnas: path,sqale_min,complexity,coverage,sonar_severity
    else:
        print(f"  AVISO: sin token ({c['sonar']['token_env']}) ni {manual}: complexity/coverage/P_hours quedaran vacios.")
        sq = pd.DataFrame(columns=["path", "sqale_min", "complexity", "coverage", "sonar_severity"])
    df = df.merge(sq, on="path", how="left")
    df["P_hours"] = df["sqale_min"] / 60.0
    df.insert(0, "repo", n)
    cols = ["repo", "path", "churn", "change_freq", "issue_density", "complexity", "coupling", "coverage",
            "P_hours", "sonar_severity", "future_defects", "future_changes"]
    df[cols].to_csv(ruta("datos", "archivos", f"{n}.csv"), index=False)
    print(f"  {len(df)} archivos | con deuda SQALE: {int((df['P_hours'] > 0).sum())} | "
          f"con defectos futuros: {int((df['future_defects'] > 0).sum())}")

print("\nSIGUIENTE: python scripts/03_muestrear_y_generar_paneles.py")
