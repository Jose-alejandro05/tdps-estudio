# Pre-registro — Validación del TDPS (completar antes de extraer datos)

**Fecha de registro:** ____   **Autores:** ____   **Plataforma/DOI:** OSF / AsPredicted ____

## 1. Hipótesis y umbrales (fijados antes de ver datos)
- **H1 (concordancia con expertos):** ρ de Spearman TDPS–consenso ≥ 0,60 y límite inferior del IC95 % (bootstrap por clúster) > 0,50.
- **H2 (superioridad frente a resultados reales):** el TDPS supera a cada línea base en NDCG@10 y precision@10 (Wilcoxon pareado por repo, Holm, α = 0,05).
- **H3 (robustez):** con pesos perturbados ±20 %, ρ ≥ 0,80 en ≥ 95 % de 1 000 escenarios.
- **H4 (campo, opcional):** ____

## 2. Diseño
- t0 = ____ ; t1 = ____ ; ventana de historial previo = ____ meses.
- Repositorios (nombre, URL, criterios de selección y de exclusión): ____
- Unidad de deuda técnica: archivo con deuda SQALE > 0.
- Ítems por repositorio: ____ (muestreo aleatorio, semilla ____).

## 3. Operacionalización
- I = promedio de min-max(churn, frecuencia de cambio, issue_density); R = promedio de min-max(complejidad, acoplamiento) y 1 − min-max(cobertura).
- TDPS = (wI·I + wR·R + wV·V) / (wP·max(P,0,1) + wE·max(E,0,1)); pesos por AHP (agregación AIJ).
- Proxy de acoplamiento: ____ ; proxy de issue_density: ____ ; criterio de defecto futuro: ____
- "Alto riesgo" = ≥ cuartil superior de defectos futuros por repositorio (mínimo 1). k = 10.

## 4. Muestras
- Panel AHP: n = ____ (criterios de inclusión: ____). Regla: se revisan matrices con CR ≥ 0,10.
- Panel de validación: n ≥ 10, disjunto del AHP, ciego a puntajes; bloques de ____ ítems.
- Puntuadores de V y E_sp: n = ____ (ciegos a resultados futuros).

## 5. Análisis
Spearman/Kendall con IC bootstrap; W de Kendall por bloque; precision@k, NDCG@k, AUC; Wilcoxon + Holm; Monte Carlo ±20 %;
ablación; normalización alterna (rangos); pesos individuales por experto. Software: `tdps_experimento.py` (versión/hash ____).

## 6. Criterios de exclusión y desviaciones
Exclusiones de datos: ____ . Toda desviación se declarará en el artículo.

## 7. Ética
Aprobación del comité: ____ ; consentimiento informado: sí/no.
