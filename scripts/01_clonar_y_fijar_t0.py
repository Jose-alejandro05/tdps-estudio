#!/usr/bin/env python3
"""Paso 1: clona los repos, fija el commit de t0 y prepara sonar-project.properties."""
import os
import subprocess
import sys

import pandas as pd
from comun import cfg, fin_dia, git, ruta

c = cfg()
os.makedirs(ruta("repos"), exist_ok=True)
os.makedirs(ruta("datos"), exist_ok=True)
filas = []
for r in c["repos"]:
    if "ORG/REPO" in r["url"]:
        sys.exit("Edite config.json: reemplace las URL de ejemplo por los repositorios reales.")
    dest = ruta("repos", r["nombre"])
    if not os.path.isdir(dest):
        print(f"Clonando {r['nombre']} ...")
        subprocess.run(["git", "clone", "--quiet", r["url"], dest], check=True)
    else:
        subprocess.run(["git", "-C", dest, "fetch", "--all", "--quiet"], check=True)
    ref = git(dest, "symbolic-ref", "refs/remotes/origin/HEAD").strip()   # rama por defecto
    h0 = git(dest, "rev-list", "-n", "1", f"--before={fin_dia(c['t0'])}", ref).strip()
    if not h0:
        sys.exit(f"{r['nombre']}: no hay commits anteriores a t0={c['t0']}.")
    subprocess.run(["git", "-C", dest, "checkout", "--quiet", h0], check=True)
    fecha = git(dest, "show", "-s", "--format=%cI", h0).strip()
    n_pre = int(git(dest, "rev-list", "--count", h0).strip())
    n_post = int(git(dest, "rev-list", "--count", ref, f"--after={fin_dia(c['t0'])}",
                     f"--before={fin_dia(c['t1'])}").strip())
    if n_post < 20:
        print(f"  AVISO {r['nombre']}: solo {n_post} commits entre t0 y t1; el criterio de resultados sera pobre.")
    with open(os.path.join(dest, "sonar-project.properties"), "w", encoding="utf-8") as f:
        f.write(f"sonar.projectKey={r['sonar_key']}\nsonar.sources=.\n"
                "sonar.exclusions=**/test/**,**/tests/**,**/node_modules/**,**/*.spec.ts,**/*.test.ts\n"
                "sonar.java.binaries=.\n"
                f"sonar.host.url={c['sonar']['url']}\n"
                "# AGREGUE su reporte de cobertura, p.ej.:\n"
                "# sonar.coverage.jacoco.xmlReportPaths=target/site/jacoco/jacoco.xml\n"
                "# sonar.javascript.lcov.reportPaths=coverage/lcov.info\n")
    filas.append({"repo": r["nombre"], "url": r["url"], "sonar_key": r["sonar_key"], "commit_t0": h0,
                  "fecha_commit_t0": fecha, "commits_hasta_t0": n_pre, "commits_t0_a_t1": n_post})
    print(f"  {r['nombre']}: commit_t0={h0[:10]} ({fecha[:10]})")

pd.DataFrame(filas).to_csv(ruta("datos", "repos_commits.csv"), index=False)
print("\nGuardado datos/repos_commits.csv (publiquelo con el estudio).")
print("SIGUIENTE: compile cada repo, genere cobertura y ejecute sonar-scanner dentro de repos/<R>/")
print("           (ver README, paso 4). Luego: python scripts/02_extraer_metricas.py")
