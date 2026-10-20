#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diseño de experimento para validar el TDPS (Technical Debt Priority Score).

Fases:
  A. Pesos AHP (CR individual, agregación AIJ por media geométrica)
  B. Validación frente a expertos (Spearman/Kendall con bootstrap por clúster, W de Kendall)
  C. Validación frente a resultados reales posteriores a t0 (precision@k, NDCG@k, AUC)
  D. Líneas base, sensibilidad Monte Carlo, ablación, Wilcoxon + Holm

USO
  python tdps_experimento.py --demo                  # SOLO prueba el código (datos sintéticos)
  python tdps_experimento.py --data ./datos --out ./resultados   # datos reales

ARCHIVOS DE ENTRADA (carpeta --data)
  ahp_expertos.csv      experto, i, j, valor     (comparaciones pareadas Saaty; i,j in I,R,V,P,E)
  items.csv             item_id, repo, churn, change_freq, issue_density,      <- hasta t0
                        complexity, coupling, coverage,                         <- SonarQube hasta t0
                        V, P_hours, E_sp, sonar_severity,                       <- PO / SQALE / equipo
                        future_defects, future_changes                          <- SOLO despues de t0
  ranking_expertos.csv  evaluador, item_id, rank   (1 = mas prioritario; panel DISTINTO al AHP)

ADVERTENCIA: los resultados son reales solo si items.csv y los CSV de expertos vienen de
datos reales. Nada posterior a t0 puede alimentar I, R, V, P ni E (fuga de informacion).
"""
import argparse
import json
import os
import warnings
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=RuntimeWarning)

SEED = 42
CRIT = ["I", "R", "V", "P", "E"]
RI = {1: 0, 2: 0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45}
SAATY = np.array([1/9, 1/8, 1/7, 1/6, 1/5, 1/4, 1/3, 1/2, 1, 2, 3, 4, 5, 6, 7, 8, 9])
FLOOR = 0.1   # piso para P y E normalizados (evita division por ~0)
N_MC = 1000
TOPK = 10
HIGH_Q = 0.75  # "alto riesgo" = cuartil superior de defectos futuros dentro de cada repo


# ----------------------------------------------------------------------------
# Fase A: AHP
# ----------------------------------------------------------------------------
def matriz_ahp(df_exp):
    n = len(CRIT)
    A = np.ones((n, n))
    for _, r in df_exp.iterrows():
        i, j = CRIT.index(r["i"]), CRIT.index(r["j"])
        A[i, j], A[j, i] = r["valor"], 1 / r["valor"]
    return A


def pesos_cr(A):
    vals, vecs = np.linalg.eig(A)
    k = np.argmax(vals.real)
    w = np.abs(vecs[:, k].real)
    w = w / w.sum()
    n = A.shape[0]
    ci = (vals[k].real - n) / (n - 1)
    return w, ci / RI[n]


def fase_a(ahp):
    mats, filas = {}, []
    for e, g in ahp.groupby("experto"):
        A = matriz_ahp(g)
        w, cr = pesos_cr(A)
        mats[e] = A
        filas.append({"experto": e, "CR": cr, "consistente": cr < 0.10,
                      **{f"w_{c}": x for c, x in zip(CRIT, w)}})
    ind = pd.DataFrame(filas)
    ok = [e for e, c in zip(ind["experto"], ind["CR"]) if c < 0.10]
    usar = ok if ok else list(mats)
    G = np.exp(np.mean([np.log(mats[e]) for e in usar], axis=0))   # AIJ: media geometrica
    w, cr = pesos_cr(G)
    resumen = {"n_expertos": len(mats), "n_consistentes": len(ok),
               "CR_agregado": float(cr), "pesos": dict(zip(CRIT, map(float, w)))}
    return w, resumen, ind


# ----------------------------------------------------------------------------
# TDPS
# ----------------------------------------------------------------------------
def minmax(s):
    r = s.max() - s.min()
    return (s - s.min()) / r if r > 0 else s * 0


def rankpct(s):
    return s.rank(pct=True)


def componentes(df, norm="minmax"):
    f = minmax if norm == "minmax" else rankpct
    c = pd.DataFrame(index=df.index)
    c["I"] = np.mean([f(df["churn"]), f(df["change_freq"]), f(df["issue_density"])], axis=0)
    c["R"] = np.mean([f(df["complexity"]), f(df["coupling"]), 1 - f(df["coverage"])], axis=0)
    c["V"] = f(df["V"])
    c["P"] = f(df["P_hours"])
    c["E"] = f(df["E_sp"])
    return c


def tdps(c, w):
    w = dict(zip(CRIT, w))
    num = w["I"] * c["I"] + w["R"] * c["R"] + w["V"] * c["V"]
    den = w["P"] * c["P"].clip(lower=FLOOR) + w["E"] * c["E"].clip(lower=FLOOR)
    return num / den


# ----------------------------------------------------------------------------
# Metricas
# ----------------------------------------------------------------------------
def precision_at_k(score, rel, k=TOPK):
    idx = np.argsort(-np.asarray(score), kind="stable")[:k]
    return float(np.mean(np.asarray(rel)[idx]))


def ndcg_at_k(score, gain, k=TOPK):
    gain = np.asarray(gain, float)
    idx = np.argsort(-np.asarray(score), kind="stable")[:k]
    disc = 1 / np.log2(np.arange(2, len(idx) + 2))
    dcg = np.sum(gain[idx] * disc)
    ideal = np.sort(gain)[::-1][:k]
    idcg = np.sum(ideal * disc[:len(ideal)])
    return float(dcg / idcg) if idcg > 0 else np.nan


def auc(score, rel):
    rel = np.asarray(rel).astype(bool)
    n1, n0 = rel.sum(), (~rel).sum()
    if n1 == 0 or n0 == 0:
        return np.nan
    r = stats.rankdata(score)
    return float((r[rel].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def holm(pvals):
    p = np.asarray(pvals, float)
    order = np.argsort(p)
    adj = np.empty_like(p)
    prev = 0
    for rank, i in enumerate(order):
        prev = max(prev, (len(p) - rank) * p[i])
        adj[i] = min(1, prev)
    return adj


# ----------------------------------------------------------------------------
# Fase C + lineas base
# ----------------------------------------------------------------------------
def metodos(df, w, c):
    rng = np.random.default_rng(SEED)
    wsjf = (c["V"] + c["R"] + c["I"]) / c["E"].clip(lower=FLOOR)
    m = {
        "TDPS": tdps(c, w),
        "TDPS_pesos_iguales": tdps(c, np.ones(5) / 5),
        "SonarQube_severidad": df["sonar_severity"],
        "SQALE_principal": df["P_hours"],
        "WSJF": wsjf,
    }
    return m, rng


def evaluar_repo(g, score):
    """g: items de un repo; score: Serie con el mismo indice."""
    thr = max(g["future_defects"].quantile(HIGH_Q), 1)   # al menos 1 defecto futuro
    rel = (g["future_defects"] >= thr).astype(int)
    s = score.loc[g.index]
    return {"precision@k": precision_at_k(s, rel), "ndcg@k": ndcg_at_k(s, g["future_defects"]),
            "auc": auc(s, rel)}


def fase_c(df, w):
    c = componentes(df)
    ms, rng = metodos(df, w, c)
    filas = []
    for repo, g in df.groupby("repo"):
        for nombre, sc in ms.items():
            filas.append({"repo": repo, "metodo": nombre, **evaluar_repo(g, sc)})
        # aleatorio: promedio de 1000 permutaciones
        accs = [evaluar_repo(g, pd.Series(rng.random(len(g)), index=g.index)) for _ in range(N_MC)]
        filas.append({"repo": repo, "metodo": "Aleatorio",
                      **{k: float(np.nanmean([a[k] for a in accs])) for k in accs[0]}})
    res = pd.DataFrame(filas)
    medias = res.groupby("metodo")[["precision@k", "ndcg@k", "auc"]].agg(["mean", "std"])

    # Wilcoxon pareado por repo: TDPS vs cada linea base (con Holm)
    comp = []
    for met in ["precision@k", "ndcg@k", "auc"]:
        piv = res.pivot(index="repo", columns="metodo", values=met)
        bases = [b for b in piv.columns if b not in ("TDPS",)]
        ps = []
        for b in bases:
            d = piv["TDPS"] - piv[b]
            try:
                p = stats.wilcoxon(d, alternative="greater").pvalue if (d != 0).any() else 1.0
            except ValueError:
                p = np.nan
            ps.append(p)
        adj = holm(np.nan_to_num(ps, nan=1.0))
        for b, p, pa in zip(bases, ps, adj):
            comp.append({"metrica": met, "vs": b, "dif_media": float((piv["TDPS"] - piv[b]).mean()),
                         "p_wilcoxon": p, "p_holm": pa})
    return res, medias, pd.DataFrame(comp)


# ----------------------------------------------------------------------------
# Fase B: expertos
# ----------------------------------------------------------------------------
def kendall_w(R):
    """R: matriz evaluadores x items con rangos 1..n (diseño completo, sin correccion de empates)."""
    m, n = R.shape
    S = np.sum((R.sum(axis=0) - m * (n + 1) / 2) ** 2)
    return float(12 * S / (m ** 2 * (n ** 3 - n)))


def acuerdo_evaluadores(rk, piv):
    """W de Kendall: por bloque si existe columna 'bloque'; si no, sobre la matriz completa."""
    if "bloque" in rk.columns:
        ws = []
        for b, g in rk.groupby("bloque"):
            m = g.pivot_table(index="evaluador", columns="item_id", values="rank")
            if m.shape[0] >= 3 and not m.isna().any().any():
                ws.append(kendall_w(m.rank(axis=1).values))
        return {"W_kendall_media_por_bloque": float(np.mean(ws)) if ws else None,
                "W_kendall_n_bloques": len(ws)}
    if not piv.isna().any().any():
        return {"W_kendall": kendall_w(piv.values)}
    return {"W_kendall": None}


def fase_b(df, rk, w, n_boot=2000):
    rng = np.random.default_rng(SEED)
    piv = rk.pivot_table(index="evaluador", columns="item_id", values="rank", aggfunc="mean")
    comunes = [i for i in df["item_id"] if i in piv.columns and piv[i].notna().any()]
    piv = piv[comunes]
    d = df.set_index("item_id").loc[comunes]
    # el TDPS se normaliza con TODOS los items, luego se seleccionan los evaluados
    score_all = pd.Series(tdps(componentes(df), w).values, index=df["item_id"])
    score = score_all.loc[comunes].values
    consenso = -np.nanmean(piv.values, axis=0)     # mayor = mas prioritario (rank menor)

    rho = stats.spearmanr(score, consenso)
    tau = stats.kendalltau(score, consenso)
    base_sonar = stats.spearmanr(d["sonar_severity"].values, consenso)[0]

    repos = d["repo"].values
    ur = np.unique(repos)
    boots = []
    for _ in range(n_boot):
        rs = rng.choice(ur, len(ur), replace=True)
        idx = np.concatenate([np.where(repos == r)[0] for r in rs])
        es = rng.choice(piv.shape[0], piv.shape[0], replace=True)
        cons = -np.nanmean(piv.values[es], axis=0)
        ok = np.isfinite(cons[idx])
        if ok.sum() > 5:
            r_ = stats.spearmanr(score[idx][ok], cons[idx][ok])[0]
            if not np.isnan(r_):
                boots.append(r_)
    ic = np.percentile(boots, [2.5, 97.5])
    out = {"n_items": len(comunes), "n_evaluadores": int(piv.shape[0]),
           "spearman": float(rho[0]), "spearman_p": float(rho[1]),
           "spearman_IC95_boot": [float(ic[0]), float(ic[1])],
           "kendall_tau": float(tau[0]), "kendall_p": float(tau[1]),
           "spearman_SonarQube_vs_expertos": float(base_sonar)}
    out.update(acuerdo_evaluadores(rk, piv))
    return out


# ----------------------------------------------------------------------------
# Sensibilidad, ablacion, normalizacion alternativa, pesos por experto
# ----------------------------------------------------------------------------
def sensibilidad(df, w):
    rng = np.random.default_rng(SEED)
    c = componentes(df)
    base = tdps(c, w)
    rhos = []
    for _ in range(N_MC):
        wp = w * rng.uniform(0.8, 1.2, 5)
        wp = wp / wp.sum()
        rhos.append(stats.spearmanr(base, tdps(c, wp))[0])
    rhos = np.array(rhos)
    return {"media": float(rhos.mean()), "min": float(rhos.min()), "p5": float(np.percentile(rhos, 5)),
            "prop_rho>=0.80": float((rhos >= 0.80).mean())}


def ablacion(df, w):
    c = componentes(df)

    def desempeno(wv):
        sc = tdps(c, wv)
        return np.nanmean([evaluar_repo(g, sc)["ndcg@k"] for _, g in df.groupby("repo")])

    base = desempeno(w)
    filas = [{"componente_quitado": "ninguno", "ndcg@k": base, "caida": 0.0}]
    for k, nom in enumerate(CRIT):
        wv = w.copy()
        wv[k] = 0
        wv = wv / wv.sum()
        d = desempeno(wv)
        filas.append({"componente_quitado": nom, "ndcg@k": d, "caida": base - d})
    return pd.DataFrame(filas)


def normalizacion_alterna(df, w):
    a = tdps(componentes(df, "minmax"), w)
    b = tdps(componentes(df, "rank"), w)
    return {"spearman_minmax_vs_rank": float(stats.spearmanr(a, b)[0])}


def pesos_por_experto(df, ind):
    c = componentes(df)
    base = None
    out = []
    ws = ind[[f"w_{k}" for k in CRIT]].values
    wm = ws.mean(axis=0)
    base = tdps(c, wm)
    for e, wi in zip(ind["experto"], ws):
        out.append({"experto": e, "spearman_vs_pesos_medios": float(stats.spearmanr(base, tdps(c, wi))[0])})
    return pd.DataFrame(out)


# ----------------------------------------------------------------------------
# Datos sinteticos (SOLO para probar el codigo)
# ----------------------------------------------------------------------------
def datos_demo(n_repos=8, n_items=14):
    rng = np.random.default_rng(SEED)
    filas = []
    for r in range(n_repos):
        for i in range(n_items):
            riesgo = rng.normal()
            interes = rng.normal()
            filas.append({
                "item_id": f"R{r}-{i}", "repo": f"R{r}",
                "churn": np.exp(5 + 0.6 * interes + rng.normal(0, .5)),
                "change_freq": np.exp(2 + 0.5 * interes + rng.normal(0, .4)),
                "issue_density": np.exp(0 + 0.4 * interes + rng.normal(0, .5)),
                "complexity": np.exp(2.5 + 0.6 * riesgo + rng.normal(0, .4)),
                "coupling": np.exp(1.5 + 0.5 * riesgo + rng.normal(0, .5)),
                "coverage": np.clip(70 - 12 * riesgo + rng.normal(0, 10), 0, 100),
                "V": rng.integers(1, 6), "P_hours": np.exp(1.5 + rng.normal(0, .8)),
                "E_sp": rng.choice([1, 2, 3, 5, 8, 13]), "sonar_severity": rng.integers(1, 6),
                "future_defects": rng.poisson(np.exp(0.6 * riesgo + 0.3 * interes)),
                "future_changes": rng.poisson(np.exp(1 + 0.5 * interes)),
                "_latent": 0.55 * riesgo + 0.3 * interes + 0.15 * rng.normal()})
    df = pd.DataFrame(filas)

    w_true = np.array([.18, .31, .27, .13, .11])
    rows = []
    for e in range(12):
        for a, b in combinations(range(5), 2):
            v = w_true[a] / w_true[b] * np.exp(rng.normal(0, .35))
            v = SAATY[np.argmin(np.abs(np.log(SAATY) - np.log(v)))]
            rows.append({"experto": f"E{e+1}", "i": CRIT[a], "j": CRIT[b], "valor": v})
    ahp = pd.DataFrame(rows)

    rk = []
    for e in range(10):
        s = df["_latent"] + rng.normal(0, .5, len(df))
        rank = stats.rankdata(-s)
        rk += [{"evaluador": f"X{e+1}", "item_id": it, "rank": rr} for it, rr in zip(df["item_id"], rank)]
    return df.drop(columns="_latent"), ahp, pd.DataFrame(rk)


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="datos")
    ap.add_argument("--out", default="resultados")
    ap.add_argument("--demo", action="store_true", help="datos sinteticos: SOLO para probar el codigo; NO usar para resultados")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    if a.demo:
        print("=" * 70 + "\nMODO DEMO: datos SINTETICOS. No reportar estos numeros como resultados.\n" + "=" * 70)
        df, ahp, rk = datos_demo()
    else:
        df = pd.read_csv(os.path.join(a.data, "items.csv"))
        ahp = pd.read_csv(os.path.join(a.data, "ahp_expertos.csv"))
        rk = pd.read_csv(os.path.join(a.data, "ranking_expertos.csv"))

    req = ["item_id", "repo", "churn", "change_freq", "issue_density", "complexity", "coupling", "coverage",
           "V", "P_hours", "E_sp", "sonar_severity", "future_defects", "future_changes"]
    falt = [c for c in req if c not in df.columns]
    if falt or df[req].isna().any().any():
        raise SystemExit(f"items.csv incompleto (faltan columnas {falt} o hay celdas vacias). "
                         "Ejecuten scripts/05_validar_datos.py")
    w, resumen_a, ind = fase_a(ahp)
    ind.to_csv(os.path.join(a.out, "A_ahp_individual.csv"), index=False)
    print("\n[Fase A] Pesos AHP:", json.dumps(resumen_a, indent=2, ensure_ascii=False))

    rb = fase_b(df, rk, w)
    print("\n[Fase B] Validacion vs expertos:", json.dumps(rb, indent=2, ensure_ascii=False))

    res, medias, comp = fase_c(df, w)
    res.to_csv(os.path.join(a.out, "C_metricas_por_repo.csv"), index=False)
    comp.to_csv(os.path.join(a.out, "C_comparaciones_wilcoxon_holm.csv"), index=False)
    print("\n[Fase C] Desempeño vs resultados reales posteriores a t0:\n", medias.round(3))
    print("\nTDPS vs lineas base (Wilcoxon por repo, Holm):\n", comp.round(4).to_string(index=False))
    if df["repo"].nunique() < 8:
        print("\nAVISO: con <8 repos, Wilcoxon no puede alcanzar significancia; reporten tamaños del efecto.")

    sens = sensibilidad(df, w)
    abl = ablacion(df, w)
    norm = normalizacion_alterna(df, w)
    exp = pesos_por_experto(df, ind)
    abl.to_csv(os.path.join(a.out, "D_ablacion.csv"), index=False)
    exp.to_csv(os.path.join(a.out, "D_pesos_por_experto.csv"), index=False)
    print("\n[Sensibilidad Monte Carlo ±20%]:", json.dumps(sens, indent=2))
    print("\n[Ablacion]\n", abl.round(3).to_string(index=False))
    print("\n[Normalizacion alterna]:", norm)
    print("\n[Pesos de cada experto vs pesos medios]\n", exp.round(3).to_string(index=False))

    with open(os.path.join(a.out, "resumen.json"), "w", encoding="utf-8") as f:
        json.dump({"A": resumen_a, "B": rb, "sensibilidad": sens, "normalizacion": norm,
                   "demo": a.demo}, f, indent=2, ensure_ascii=False)
    print(f"\nResultados guardados en {a.out}/")


if __name__ == "__main__":
    main()
