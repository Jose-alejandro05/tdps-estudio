# Estudio de validación del TDPS — paquete de ejecución

Esta carpeta contiene todo lo necesario para **ejecutar** el estudio con datos reales. El paquete no trae datos ni
resultados: cada número que obtengan saldrá de sus repositorios y de sus paneles de expertos.

## Requisitos
Python ≥ 3.10, Git, Docker (para SonarQube) y `pip install -r requirements.txt`.

## Estructura
```
config.json                    ← EDITAR (fechas, repos, tamaños)
scripts/01..05_*.py            ← pipeline
tdps_experimento.py            ← análisis estadístico (Fases A-D)
formularios/                   ← HTML para los paneles (AHP y ranking)
paneles/                       ← hojas y asignaciones generadas
respuestas/{ahp,puntuacion,ranking}/   ← aquí se depositan las respuestas
datos/                         ← CSV finales que lee el análisis
resultados/                    ← salidas del análisis
plantillas/                    ← formato de cada CSV
docs/preregistro_plantilla.md  ← completar y registrar ANTES de extraer datos
```

## Procedimiento

**0. Pre-registro.** Complete `docs/preregistro_plantilla.md` y regístrelo en OSF/AsPredicted *antes* del paso 1.

**1. Configurar.** En `config.json` fije `t0`, `t1` (≥ 12 meses después de t0), y reemplace los `repos` de ejemplo por
8–10 repositorios reales (Java/TypeScript, 50–500 KLOC, > 3 años de historial, actividad reciente).
Ajuste `n_evaluadores` (≥ 10) y `evaluadores_por_bloque` (≥ 3; recomendado 5–6).

**2. Clonar y fijar t0.**
```bash
python scripts/01_clonar_y_fijar_t0.py
```
Deja cada repo en el commit de t0 y crea `datos/repos_commits.csv` y un `sonar-project.properties`.

**3. SonarQube.**
```bash
docker run -d --name sonarqube -p 9000:9000 sonarqube:10-community
```
Entre a http://localhost:9000, cree un token y expórtelo: `export SONAR_TOKEN=...`.
Para cada repo (que está en el commit de t0): compile, genere cobertura (JaCoCo / lcov), agregue la ruta del reporte en su
`sonar-project.properties` y ejecute `sonar-scanner`. Sin cobertura, `coverage` quedará vacío y el paso 5 lo rechazará.
*Alternativa sin API:* exporte las métricas a `datos/sonar_manual/<REPO>.csv` (formato en `plantillas/sonar_manual_REPO.csv`).

**4. Extraer métricas.**
```bash
python scripts/02_extraer_metricas.py
```
Predictores: solo historial hasta t0. Resultados (`future_defects`, `future_changes`): solo entre t0 y t1.
Proxies usados (decláralos en el artículo): `coupling` = nº de imports distintos; `issue_density` = nº de commits previos
que referencian `#N`; `future_defects` = commits posteriores con mensaje de corrección (regex en `config.json`).
Si pueden enlazar issues etiquetados como *bug* o aplicar SZZ, reemplacen `future_defects` y documenten el cambio.

**5. Muestrear ítems y generar paneles.**
```bash
python scripts/03_muestrear_y_generar_paneles.py
```
Genera `datos/items.csv` (con V y E_sp vacíos), las hojas y los formularios.

**6. Recolectar datos de los paneles** (consentimiento informado y aprobación del comité de ética antes de invitar personas):
- **Panel AHP** (12–15 expertos, ≥ 5 años en Scrum): envíe `formularios/formulario_ahp.html`. Cada experto devuelve
  un `ahp_<código>.csv` → carpeta `respuestas/ahp/`.
- **V y E_sp** (2–3 puntuadores, ciegos a los resultados futuros): envíe `paneles/items_para_puntuar.csv`; cada uno completa
  V (1–5) y E_sp (1,2,3,5,8,13,21) y lo devuelve como `<código>.csv` → `respuestas/puntuacion/`.
- **Panel de validación** (≥ 10 evaluadores **distintos** a los del AHP): según `paneles/asignacion_bloques.csv`, envíe a cada
  evaluador **solo** sus `formularios/ranking_<bloque>.html`. Devuelven CSV → `respuestas/ranking/`.
  No les muestre puntajes del TDPS ni de SonarQube.

**7. Consolidar y validar.**
```bash
python scripts/04_consolidar_respuestas.py     # reporta CR por experto: si CR ≥ 0,10, pídale revisar y reenvíe
python scripts/05_validar_datos.py             # debe terminar sin ERRORES
```

**8. Analizar.**
```bash
python tdps_experimento.py --data datos --out resultados
```
Salidas: `resumen.json`, `A_ahp_individual.csv`, `C_metricas_por_repo.csv`, `C_comparaciones_wilcoxon_holm.csv`,
`D_ablacion.csv`, `D_pesos_por_experto.csv`.

**9. Reportar.** Compare con los umbrales pre-registrados y reporte todo, incluidos los resultados negativos.
Reemplace en el artículo las cifras de las Tablas 3 y 4 y del resumen. Publique `datos/`, los scripts, `config.json` y
`datos/repos_commits.csv` en Zenodo (anonimizando códigos de personas).

## Reglas para que los resultados sean reales
1. Nada posterior a t0 entra en I, R, V, P ni E.
2. Paneles AHP y de validación disjuntos; evaluadores ciegos a los puntajes.
3. No modificar umbrales, filtros ni `HIGH_Q`/`TOPK` después de ver resultados.
4. No usar `--demo` para nada que no sea probar el código: genera datos sintéticos.
5. Con < 8 repositorios la comparación por repositorio tiene poca potencia (el script avisa).

## Lectura de resultados
- `W_kendall_media_por_bloque` < 0,5 → el juicio experto no es una referencia estable.
- `D_ablacion.csv`: caída de NDCG < 0 al quitar un componente → ese componente no aporta en sus datos.
- `spearman_IC95_boot` incluye valores < 0,50 → no se sostiene H1 con los umbrales propuestos.
