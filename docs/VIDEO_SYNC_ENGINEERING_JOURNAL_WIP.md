# GPIS / Coorte RG2019 — Bitácora técnica de sincronización de vídeos (DOCUMENTO VIVO)

> **Estado:** BORRADOR / WIP — no representa autorización de producción.
> **Versión del documento:** 0.1 — 2026-10-30 (America/Sao_Paulo).
> **Propósito:** memoria verificable, transferible a otra IA o equipo, de **qué se hizo, cuándo, cómo, por qué, con qué evidencia, qué falló y qué no se debe repetir**. Se completará a medida que se validen las etapas. El README definitivo solo se emitirá cuando la sincronización real esté científicamente verificada.
> **Repositorio:** https://github.com/chlmz/research-video-sync
> **Base documental del desarrollo actual:** commit `a21279d6c7313d65eb1239e70f1bae3ae62b1420` (PR #7, draft).
> **Precaución:** el repositorio es público. No almacenar vídeos, audio identificable, IDs de participantes, credenciales, hashes identificables de muestras reales ni información sensible.

## 0. Cómo leer y mantener esta bitácora

Cada afirmación importante debe indicar su clase de evidencia:

- **[CODE]** comprobado leyendo código, commits o tests del repositorio.
- **[CI]** observado en GitHub Actions; confirma comportamiento con fixtures, **no** con material real.
- **[FIELD REPORT]** informado por la ejecución de Work o por el responsable de la investigación; no siempre reproducible desde GitHub.
- **[MANUAL]** observación visual/auditiva del responsable científico.
- **[HYPOTHESIS]** explicación posible, pendiente de contrastación.
- **[OPEN]** decisión, validación o implementación aún no completada.

No convertir una hipótesis en hecho porque una versión posterior del código parezca resolverla. Al actualizar, añadir entradas de cronología, referencias a SHA/PR y resultados nuevos; **preservar los errores y el motivo de las decisiones**. Separar explícitamente éxito técnico, sincronización científica y autorización de producción.

## 1. Objetivo científico y salidas

Sincronizar dos vistas audiovisuales de una interacción madre-niño que pudieron comenzar en momentos diferentes. En el flujo previsto, generar tres productos por **participante / sesión / juego**:

1. Vista de la madre sincronizada: `<ID>_mom_synced.mp4`.
2. Vista del niño sincronizada: `<ID>_child_synced.mp4`.
3. Composición lado a lado para revisión y codificación: `<ID>_side_by_side.mp4`.

Los nombres anteriores ilustran el legado. En producción, **la ruta/nombre deben incluir identidad de sesión y juego** para impedir colisiones cuando una persona tenga varios juegos o visitas. Esta política definitiva está **[OPEN]**.

El éxito requiere mucho más que crear MP4: fuentes correctas, sesión inequívoca, entrega íntegra, desfase estimado con evidencia, conversión técnicamente válida, ausencia de deriva inaceptable, QC científico y publicación trazable.

No se permite inferir que dos vídeos son del mismo juego por fecha, orden `SNAP`, código de cámara A/B o cercanía de rutas.

## 2. Línea de tiempo de decisiones y evidencia

### 2026-09-02 — scripts iniciales (`v1.0`)

- [CODE] Se publicó `sync_research_project.sh` en el commit `0d3eedf23f1b8c2b9314e475dbf5eca89787c06c`, mensaje «Initial upload - working pipeline v1.0». Referencia: https://github.com/chlmz/research-video-sync/blob/0d3eedf23f1b8c2b9314e475dbf5eca89787c06c/sync_research_project.sh
- [CODE] Se publicó `sync_videos.sh` también en septiembre; referencia histórica: https://github.com/chlmz/research-video-sync/blob/e339d2d3e86dfe8a30bcd7b2cf3327fda68602e8/sync_videos.sh
- [MANUAL] El responsable relata resultados excelentes con los pilotos de septiembre. Aún falta identificar qué ejecuciones y archivos concretos usaron cada script y si se revisó el desfase de manera independiente.
- [CODE] El script `sync_research_project.sh` extraía audio WAV mono a **16 kHz**, calculaba correlación cruzada **FFT de las señales completas** con NumPy y elegía el máximo global; no imponía un límite fijo de búsqueda en ese camino. Después recortaba la cámara que tenía material inicial adicional y exportaba dos MP4 y composición lado a lado.
- [CODE] **Convención del signo correcta** para la ruta NumPy de ese script, comprobada después por tests. En cambio `sync_videos.sh` **recortaba la cámara equivocada** para desfases distintos de cero.
- [CODE] No copiar indiscriminadamente los Bash: la ruta sin NumPy de `sync_research_project.sh` da offsets erróneos; `set -e` junto con `((COUNTER++))` puede abortar el lote; existe selección silenciosa del primer archivo, sobrescritura con `-y`, marcadores dentro de fuentes y ausencia de QC.
- Fuente de auditoría reproducible: https://github.com/chlmz/research-video-sync/blob/a21279d6c7313d65eb1239e70f1bae3ae62b1420/docs/LEGACY_AUDIT.md y `tests/test_legacy_audit.py`.

### 2026-09-29 — transición al pipeline Python

- [CODE] La rama principal histórica `a6b2a393230bbe5a08624be781897abff8b2505e` incluye `pipeline_rg2019.py` y `rg2019/{config,discovery,pipeline,media,syncest,state,statuses}.py`.
- [CODE] Se sustituyó la correlación global sin confianza por un estimador de dos etapas, ventanas independientes, umbrales de calidad, control de conflictos y reanudación.
- [CODE] El pipeline antiguo suponía un par por participante cerca de la raíz y podía **MOVER** contenido `00_INBOX → 01_RAW`. NO ejecutarlo contra la estructura profunda de campo actual, ni permitir que mueva fuentes hasta rediseñar la ingestión.
- [CODE] El ejecutor clásico puede producir los 3 MP4, pero **no equivale a que el ejecutor seguro actual esté aprobado para datos reales**.

### Octubre 2026 — protección de ingestión y procesamiento sintético

- **PR #4**: descubrimiento recursivo conservador de vídeos y clasificación por sesión/juego, sin abrir vídeo ni resolver ambigüedades automáticamente.
- **PR #5**: puertas de autorización sintética y prueba con fuentes inventadas.
- **PR #6**, head `21184f99628d8ba79cb5a8badc12cf6f8742c820`: publicación segura, scratch local, hashes, manifiesto, `COMMITTED`, intentos inmutables, idempotencia, control de rutas Windows y clasificación de errores.
- [FIELD REPORT] En Dell Windows 11, suite de regresión 264 PASS, 0 FAIL, 2 SKIP reportados; prueba funcional SMB posterior 11 controles PASS bajo una identidad de servicio sin privilegios administrativos sin elevación. La observación de identidad SMB histórica se corroboró por registros NAS del 29/10; no debe presentarse como identidad independiente registrada para **la misma** sesión SMB del 30/10.
- **PR #7** `codex/gpis-delivery-v2`, head `a21279d6c7313d65eb1239e70f1bae3ae62b1420`: manifiesto de recepción `rg2019.delivery.v2`, UUID de sesión independiente, SHA-256, materiales auxiliares, exclusiones trazadas y juego 1 inferido solo para par único en sesión revisada. [CI] Windows: 296 PASS / 0 FAIL; Ubuntu: 295 PASS / 1 SKIP. Son pruebas sintéticas, no validación con vídeos reales.
- Documentos base: `docs/PREPRODUCTION.md`, `docs/DELIVERY_V2.md`, `docs/STORAGE_PERMISSIONS.md`.
- Todos los PR anteriores permanecían en borrador en la evaluación original. No asumir despliegue ni merge por la existencia de ramas.

### 2026-10-30 — primer piloto real controlado (sin identificadores)

**[FIELD REPORT]** Se copiaron dos grabaciones explícitamente seleccionadas a un scratch local autorizado; hashes, tamaños y fechas de origen fueron comprobados sin alterar los originales. Se ejecutó la versión `a21279d6...` sin cambiar parámetros. **No publicar aquí nombres de participantes, duraciones individuales, métricas acústicas específicas ni rutas de datos reales.** Esos detalles pertenecen a los registros privados de QC.

**Metadatos técnicos de interoperabilidad:** el contenedor de campo es AVI, con vídeo H.264 y audio PCM mono. Las duraciones declaradas de las pistas pueden diferir y contener anomalías de cabecera; **la diferencia entre duraciones no es el offset entre cámaras**.

**Resultado del estimador de audio:** se pudo extraer audio, pero ninguna de las ventanas analizadas alcanzó consenso y no se aceptó desfase. No se pasó a etapa fina ni se generaron MP4 sincronizados. Los umbrales, las ventanas y la metodología son reproducibles desde el código, pero los valores medidos sobre fuentes reales permanecen privados.

**Decodificación visual:** se informaron advertencias/errores H.264 y metadatos AVI imperfectos; el reproductor pudo abrir ambas fuentes. [MANUAL] El investigador informó que las grabaciones se reproducían normalmente. Esto **no sustituye** un escaneo integral de frames o timestamps.

**Decisión:** NO cambiar solo la extensión AVI→MP4, NO recodificar originales por rutina, NO bajar umbrales ni inventar un offset. Conservar diagnósticos exclusivamente en infraestructura autorizada. QC permanece **NO APROBADO**.

**[HYPOTHESIS]** La búsqueda limitada a ±120 s puede excluir el desfase correcto. Otra posibilidad es audio poco comparable o emparejamiento de sesión incorrecto. Ninguna se ha demostrado con este par.

### 2026-10-30 23:41 (hora local) — rama nueva de búsqueda FFT global

- **[CODE]** Apareció `codex/gpis-global-fft`, commit `5cbd7ddad928d36b774476f0a34e28317fff5bc4` (2026-10-31 02:41 UTC). Referencia: https://github.com/chlmz/research-video-sync/commit/5cbd7ddad928d36b774476f0a34e28317fff5bc4 . Se creó el **[PR #9](https://github.com/chlmz/research-video-sync/pull/9)** en estado Draft, apilado sobre el PR #7; **no está integrada en `main`**.
- **[CODE]** `rg2019/syncest.py` conserva el estimador por ventanas como modo por defecto. La modalidad global es **opt-in** con `sync.global_fft_enabled=false`, máximo **3 candidatos** por defecto y presupuesto de admisión de **512 MiB**. La FFT propone picos globales con **correlación de Pearson normalizada en cada solapamiento**, usando la gama lineal correcta de desfases (corrige además el error de índice circular del Bash histórico con duraciones asimétricas).
- **[CODE]** Cada candidato debe superar validación local con ventanas **disjuntas**, umbrales de NCC, relación de picos y consenso; si no hay exactamente un candidato validado, no se aprueba desfase. Los offsets mantienen la convención madre positiva; la corrección de inicio de pistas de audio se suma una sola vez.
- **[CODE]** Se estima el costo de asignación **antes de ejecutar** la FFT, hasta un presupuesto configurado de **4096 MiB**; si excede presupuesto se rechaza la operación. Es una predicción de memoria, **no un límite de RAM impuesto por el sistema operativo**, y la opción estándar de 512 MiB puede no admitir grabaciones extensas.
- **[CODE]** Se añadieron `docs/GLOBAL_FFT.md`, `tests/test_global_fft.py` y configuración de CI para la nueva rama. Los casos sintéticos cubren desfases largos y de ambos signos, duraciones asimétricas, silencio/no-relación, periodicidad, límites de memoria, fuentes mapeadas, timestamps y una prueba a 8 kHz. **Las pruebas sintéticas deben verificarse en el CI exacto y no equivalen a QC real.**
- **[CI]** El workflow `Python tests` para ese commit arrancó 2026-10-31 02:42:49 UTC y terminó **SUCCESS** 2026-10-31 02:46:52 UTC, con ambos jobs completados satisfactoriamente (**Ubuntu 24.04 y Windows 2022**). Se verificaron sus resúmenes de job: **Windows 309 PASS, 0 errores/fallos/omisiones**; **Ubuntu 308 PASS, 1 SKIP (junction de Windows), 0 errores/fallos**. Las 13 pruebas nuevas ya están incluidas en esos totales. Fuente: https://github.com/chlmz/research-video-sync/actions/runs/41161224041 .
- **[OPEN]** PR #9 creado en Draft. Falta caracterizar consumo de memoria y ejecutar una única validación diagnóstica autorizada con audio local; ningún MP4 real se ha generado. El modo sigue apagado; la CI favorable no significa que haya generado archivos reales.

**[CODE / EJEMPLO HIPOTÉTICO]** La preadmisión de la FFT usa `192*next_fast_len(M+N-1)+64*(M+N)` bytes. Para **600 segundos combinados inventados** a 8 kHz el costo estimado es ~**1.172 MiB** de memoria adicional, fuera de audio original y overhead del runtime. Por tanto 512 y 1024 MiB no alcanzan; no cambiar presupuestos automáticamente. En el experimento Dell se deben medir la longitud real de PCM y RAM libre; no publicar metadatos reales.

### 2026-10-31 — verificación de recursos para el primer FFT global real

- **[FIELD REPORT]** Se verificaron el checkout del commit exacto del PR #9, los hashes de las copias locales AVI y los audios PCM existentes. Se comprobó de manera independiente la frecuencia/cantidad de muestras y se calculó la memoria de la FFT usando la fórmula del nuevo código.
- **[FIELD REPORT]** La RAM física disponible en ese momento era insuficiente para admitir con seguridad el espacio adicional de FFT más el margen operativo. El control de preflight se detuvo **antes de ejecutar la FFT**.
- **[SCIENTIFIC STATUS]** No se estimó ningún nuevo offset, no se evaluaron candidatos ni ventanas del nuevo algoritmo, no se generaron nuevos MP4, y el QC sigue **NotApproved**. Este bloqueo **no es evidencia de un fallo de sincronización o decodificación**.
- **[DECISION]** No reducir artificialmente el presupuesto de memoria ni usar paginación como prueba de suficiencia; observar primero qué aplicaciones prescindibles consumen memoria sin detener servicios. Si no hay margen, evaluar alternativa de FFT por bloques/streaming de memoria acotada para que el software sea reutilizable en grabaciones largas.
- **[PRIVATE]** La capacidad disponible observada, conteo de muestras, tiempos de grabación y rutas de informes reales deben conservarse en registro QC privado; **no copiarlos al repositorio público**.

### 2026-10-31 — FFT global ejecutada y rechazo por similitud acústica insuficiente

- **[FIELD REPORT]** Después de corregir el margen de RAM, se ejecutó el estimador opcional global FFT en una copia local de un par real de investigación, con el SHA exacto del PR #9 y un presupuesto de memoria revisado. La FFT terminó correctamente, sin modificar los originales.
- **[FIELD REPORT]** La primera configuración no generó candidatos elegibles. Se hizo **un único ensayo adicional** con ventanas de validación más cortas, conservando los demás umbrales de correlación y consenso. La nueva duración mínima de solapamiento permitió lags elegibles, pero el mayor pico de correlación **no superó el umbral mínimo**, y por tanto **no se aceptó ningún candidato**. El validador independiente no recibió ventanas para evaluar.
- **[SCIENTIFIC STATUS]** **Sin desfase validado; sin vídeos sincronizados; QC=NotApproved.** No clasificar el pico global rechazado como offset. El motivo observado es el rechazo por criterio de similitud, no insuficiencia de RAM ni imposibilidad geométrica de solapamiento. No se demostró que los vídeos correspondan a episodios diferentes.
- **[DECISION]** Detener barridos de parámetros y cambios de algoritmo. El siguiente paso científico es identificar al menos un evento audiovisual inequívocamente compartido entre ambas fuentes y anotar sus tiempos locales, idealmente dos eventos separados para evaluar deriva temporal. La coincidencia manual sería **un ancla diagnóstica**, no aceptación científica automática.
- **[PRIVATE]** Guardar fuera del repositorio público los tiempos individuales, picos NCC, posiciones de lag, duraciones, hashes de media, identificadores y archivos de evidencia. Aquí se documenta únicamente el razonamiento metodológico transferible a otro proyecto.

### 2026-10-31 — corrección explícita de rumbo: volver al método de septiembre (decisión del investigador)

- **[USER DECISION]** El responsable corrigió la estrategia: la técnica de **palmadas/anclas audiovisuales manuales ya se había discutido y descartado** como requisito de sincronización. No se repetirá esa propuesta como condición para avanzar. La decisión de «buscar ancla» documentada arriba queda **SUPERADA/SUSTITUIDA**; conservarla solo como evidencia de la desviación.
- **[USER DECISION]** El algoritmo que había funcionado con pilotos en septiembre, `sync_research_project.sh` (ruta NumPy), debe reutilizarse **tal como calculaba el offset**: correlación FFT del audio completo a 16 kHz, RMS normalizado, máximo global y recorte correcto, seguido de **dos MP4 y composición lateral**. No introducir en ese adaptador filtros NCC/ventanas cuya falta de candidatos impidió el ensayo.
- **[CODE]** Se implementó un adaptador independiente `sync_september_field.py` en el [PR #10 Draft](https://github.com/chlmz/research-video-sync/pull/10) sobre la rama FFT experimental. Adapta el método a participante → **sesión revisada** → subcarpetas de cámara/DCIM → juegos `mother1/children1`, `mother2/children2`. Corrige únicamente el índice FFT del lag lineal para duraciones muy desiguales, sin invertir recortes. Evita parejas ambiguas, mueve los datos **solo mediante copia verificable a scratch local** y **nunca escribe en RAW/INBOX ni NAS**.
- **[CODE/TEST]** El nuevo script crea tres MP4 y reportes JSON/CSV únicamente locales, con estado `CANDIDATE_FOR_MANUAL_QC` / `NotApproved`. **12 pruebas sintéticas focalizadas PASS**, incluida una exportación FFmpeg completa. **La primera ejecución real fue reportada posteriormente como PASS técnico, ver entrada del 31/10.** Véase [código](https://github.com/chlmz/research-video-sync/blob/codex/gpis-september-field-adapter/sync_september_field.py) y [guía](https://github.com/chlmz/research-video-sync/blob/codex/gpis-september-field-adapter/docs/SEPTEMBER_FIELD_ADAPTER.md).
- **[SCIENTIFIC DISTINCTION]** Recuperar el máximo FFT histórico no garantiza que sea un offset cierto en audios poco comparables. La decisión es **generar candidatos audiovisuales como antes para revisión posterior**, sin afirmar QC aprobado, sin usar el pico NCC previamente rechazado como offset y sin degradar el estado de evidencia/seguridad.
- **[PRODUCT LESSON]** El algoritmo y los bloqueos de recepción/infraestructura son componentes distintos: no alterar una estrategia funcional de estimación al adaptar el árbol de carpetas; aislar los nuevos controles operativos para que no invaliden un flujo que producía resultados revisables.

### 2026-10-31 — SHA incorrecto en el traspaso a Work: ejecución correctamente bloqueada

- **[HANDOFF ERROR]** Se transmitió por error un identificador de commit no existente para el adaptador de septiembre. El agente de ejecución comprobó que no existía en GitHub y detuvo el intento **sin procesar fuentes ni crear MP4**.
- **[VERIFIED FIX]** Se consultaron directamente el PR #10 y el commit de GitHub: SHA correcto `0a143d33862a274e3e9c8ed25495121218a9acac` en `codex/gpis-september-field-adapter`, PR #10 en borrador. La referencia fue corregida y el responsable autorizó continuar exclusivamente con el ensayo local previsto; el QC sigue `NotApproved` hasta tener resultados reales.
- **[LESSON]** Los traspasos a Work/Codex deben copiar el SHA exacto y verificarlo contra la rama remota/PR antes de lanzar procesamiento. Nunca reconstruir un SHA manualmente ni dar por correcto un prefijo parecido. Los errores de referencia no justifican cambiar la lógica del pipeline.

### 2026-10-31 — primer ensayo real completo del adaptador de septiembre: tres MP4 de QC generados

- **[FIELD REPORT / WORK]** Tras corregirse el SHA de traspaso y verificar el checkout del PR #10, Work ejecutó **una** prueba local del método NumPy FFT completo de septiembre sobre el par de AVI ya conservado en scratch privado. La ejecución **terminó sin error de FFmpeg** y produjo tres salidas locales: vista madre, vista niño y composición lado a lado.
- **[FIELD REPORT / WORK]** La FFT histórica produjo un desfase **positivo** y, de acuerdo con la convención verificable del script, recortó el inicio de la **madre**, sin recortar el inicio del vídeo del niño. La comprobación posterior de hashes informó que las dos copias originales permanecieron intactas. Los tiempos, rutas, SHA-256 de medios y datos individuales figuran exclusivamente en el **registro QC privado**.
- **[RESULTADO TÉCNICO]** **PASS de procesamiento/exportación real** en el adaptador histórico: tres MP4 presentes, más informe de resultado, duración y hashes, según evidencia reportada por Work. No existe todavía constancia de revisión humana independiente del sincronismo en inicio/medio/final.
- **[LÍMITE CIENTÍFICO]** El método de septiembre elige el máximo de correlación global sin superar los criterios de la vía Pearson/NCC experimentada; un resultado procesado **no equivale a un desfase científicamente validado**. Mantener `QC=NotApproved`, no usar para análisis/publicación científica y no subir esos medios al repositorio público.
- **[DECISIÓN OPERATIVA]** No cambiar el algoritmo ni repetir pruebas de RAM, red, CI o umbrales. La siguiente acción mínima es **abrir el lado a lado ya generado y observar inicio, mitad y final** para comprobar que las vistas corresponden al mismo episodio y están alineadas. No exigir palmadas ni producir nuevos eventos de calibración. Solo luego decidir promoción/escala.
- **[ALCANCE]** Este éxito usa el adaptador local PR #10; **no demuestra** que el pipeline automático anterior (que movía INBOX→RAW) ni la nueva ingestión NAS estén desplegados o autorizados.

### 2026-10-31 — confirmación visual comunicada por el investigador

- **[MANUAL / USER REPORT]** El investigador informó explícitamente que los vídeos candidatos generados por el adaptador FFT NumPy de septiembre **están sincronizados** después de su revisión visual. No se dispone en este registro público de una medición formal de error residual o deriva, ni de constancia de qué instantes concretos observó; no inventar esos detalles.
- **[STATE]** Tres MP4 ya generados localmente en el servidor, sin publicar todavía en el NAS. El reporte confirma **sincronía visual aparente**, pero no equivale por sí solo al cierre formal del `QCApproved` ni a autorización de procesamiento automático de los demás juegos. Mantener separado éxito técnico, revisión visual y disposición formal de QC.
- **[OPERATIONS]** La ausencia de vídeos en `02_SYNCED` fue explicada: el adaptador está diseñado para escribir únicamente en un directorio privado local de QC y no publica automáticamente en Synology. Abrir esa carpeta en el Explorador de Windows (no ejecutarla como comando PowerShell). La publicación futura debe ser una **copia verificada y no destructiva** cuando haya ruta, permisos y aprobación definidos.
- **[PRIVACY]** Identificadores de caso, rutas locales completas, offset, duración individual e informes técnicos siguen exclusivamente en el registro QC privado.

## 3. Matemática esencial de sincronización

### 3.1 Convención del desfase (NO cambiar sin tests)

Para un mismo evento acústico, sea `t_mom` el tiempo dentro de la grabación de la madre y `t_child` el tiempo dentro de la del niño:

```text
offset_seconds = t_mom - t_child
offset_seconds > 0  →  madre comenzó antes → RECORTAR inicio de madre
offset_seconds < 0  →  niño comenzó antes  → RECORTAR inicio de niño
offset_seconds = 0  →  no recortar
```

No recortar la cámara que *empezó después*: esa cámara ya carece del inicio adicional. El error histórico del script de dos archivos hizo exactamente eso. Incluir tests positivos, negativos y cero en toda adaptación.

### 3.2 Algoritmo original de septiembre, ruta NumPy

```python
# Resumen conceptual (no script de producción)
n = len(mom) + len(child) - 1
FA = np.fft.rfft(mom, n=n)
FB = np.fft.rfft(child, n=n)
crosscorr = np.fft.irfft(FA * np.conj(FB), n=n)
lag = np.argmax(crosscorr)
if lag > n // 2:
    lag -= n
offset_seconds = lag / sample_rate
```

Ventaja: la búsqueda de desplazamiento abarca en principio todo el audio y puede detectar desfases mayores de ±120 s.

Limitaciones: uso de memoria para señales largas; máximo global no normalizado ni contrastado; riesgo de que silencios, ruido, amplitud o períodos repetitivos produzcan un máximo espurio. **No reutilizar el offset sin control de calidad.**

### 3.3 Algoritmo actual al 30/10/2026

En `rg2019/syncest.py` con parámetros por defecto de `rg2019/config.py`:

- Entrada: extracción de primera pista de audio a **8 kHz**, mono, PCM; memmap, preénfasis y eliminación de DC.
- Etapa gruesa: hasta **7 ventanas** de **60 s**, con búsqueda dentro de **±120 s**.
- NCC mínimo de ventana **0.05**, proporción entre picos ≥ **1.5**; cluster de offsets gruesos congruentes.
- Etapa fina: hasta **5 ventanas independientes** dentro del solapamiento, búsqueda de **±2 s** alrededor del candidato, y acuerdo de al menos **3** ventanas, fracción ≥ **0.6**, con tolerancia fina **0.25 s**.
- Estima desfase constante. `offset_spread_seconds` permite observar dispersión, **no corrige deriva de relojes**.
- En la prueba real del piloto controlado no avanzó a la segunda etapa.

**[CODE / OPEN — implementación nueva sin aceptación]** La rama experimental `codex/gpis-global-fft` contiene una implementación opt-in de propuesta global FFT + validación por ventanas (SHA `5cbd7ddad928d36b774476f0a34e28317fff5bc4`). En el momento de esta revisión ya existe el PR #9 en borrador, y aún no existe una estimación FFT global aceptada sobre las fuentes reales; **CI sintética en Windows/Linux aprobada**. La aceptación científica sigue pendiente. No tratar desarrollo experimental como aprobación.

## 4. Contenedor y codificación: AVI no es un error por sí mismo

Un archivo `.avi` es un **contenedor**; H.264 es un **códec de vídeo**, y PCM un **códec de audio**. Los AVI de campo observados combinan H.264 Main y PCM. FFmpeg puede abrirlos y extraer el audio. Una advertencia de cabecera AVI, o un frame H.264 problemático, no equivalen por sí solos a pérdida de grabación.

Tampoco la reproducción visual normal demuestra integridad de todos los frames o corrección de marcas temporales.

**Diagnóstico escalonado y no destructivo:**
1. Comprobar en copias FFprobe streams, codec_tag, duración real por audio/video, timestamps, decodificación y localización de errores; separar warnings de errores reproducibles.
2. Confirmar correspondencia científica del par y sonidos comunes.
3. Estimar offset de audio con evidencia; validar que sea físicamente posible.
4. Si hiciera falta remux o transcodificación, hacerlo **solo en scratch** y dejar trazabilidad del método, no cambiar los originales ni resolver el problema alterando la extensión.
5. Revalidar audio-vídeo y QC de los resultados.

El módulo `rg2019/media.py` tiene `probe`, `extract_audio`, `encode` y `side_by_side`. La exportación normalmente vuelve a codificar la cámara que requiere recorte; puede copiar vídeo/audio sin recodificar solo cuando los codecs son compatibles con MP4. En el par actual el audio es PCM, no AAC/MP3, por lo que `can_copy` no permite copia completa directa.

## 5. Protocolo de recepción y sesión (independiente de sincronización)

Los datos de campo se organizan en `00_INBOX`, `01_RAW`, `02_SYNCED`, `03_WORKSPACE`, `04_FACEREADER_OUTPUT`, `05_ANALYTIC_DATA` y `99_LOGS_QC`; los pilotos históricos se conservan aparte. No escribir dentro de las fuentes originales.

Una auditoría de solo lectura encontró un archivo histórico heterogéneo de AVI, INSV, LRV y registros JSON de copia. Varias referencias históricas no correspondían con los archivos presentes y se identificaron cambios de nombre; los recuentos y rutas exactas permanecen en el inventario privado. Ningún indicador `copy_successful` prueba la llegada completa al NAS.

Reglas aprobadas para `delivery.v2`:

1. Identificar participante, **sesión UUID independiente** y juego. No asociar todas las visitas a un solo `session_id` de participante.
2. Emparejar `mother1/children1` y `mother2/children2` por número explícito. Juego 1 sin numeración solo si **una única pareja inequívoca** pertenece a una sesión delimitada y revisada: `game_origin=inferred_unique_pair`.
3. La herramienta de campo generará futuro manifiesto final después de fijar nombres y cerrar la selección local; incluir AVI y auxiliares pertinentes, rutas definitivas, tamaño y SHA-256, renombrados y exclusiones justificadas. El manifiesto vive fuera del alcance que certifica.
4. El NAS confirma la **recepción** únicamente si concuerdan conjunto exacto, tamaños y hashes y no hay archivos cambiantes. Llegada anticipada de manifiesto ⇒ `WaitingForDelivery`.
5. `ReceptionVerified` ≠ `QCApproved` ≠ autorización de procesamiento.
6. La integración de `Finalizar entrega` con el software real de FURG está **[OPEN]** porque todavía no se dispone de acceso al PC de campo.

## 6. Arquitectura de ejecución y límites actuales

**Propuesta operacional (aún NO modo producción):**

```text
FURG — captura/copia local → Synology Drive → NAS 00_INBOX
             ↘ manifiesto cierre (futuro)
NAS recibe y verifica entrega → inventario/sesión/juego revisados
                ↓ SOLO cuando esté autorizado
Servidor de análisis (identidad de servicio restringida) → copia verificada a scratch local
                ↓
FFmpeg extrae audio → estimador robusto → revisión de confianza
                ↓
FFmpeg produce mom_synced, child_synced, side_by_side
                ↓
QC técnico + QC científico → publicación protegida en 02_SYNCED
                ↓
Manifiesto/COMMITTED + logs, procedencia y opción de relectura
```

Estado efectivo al 30/10: el ejecutor más protegido (`rg2019.preproduction`) acepta **solo datos sintéticos**; tiene límites de 120 s por vídeo y máximo de entradas por defecto de 256 MiB, no ajustados a grabaciones de campo. El contrato `delivery.v2` no los elimina. Publicación real y procesamiento automático permanecen **bloqueados**.

`01_RAW` debe permanecer inmutable. No inferir que la identidad de entrega del equipo de campo tiene permisos seguros: la herencia de permisos de escritura detectada en RAW y pilotos requiere corrección aprobada. Ningún experimento de sincronización debe modificar ACL, mover INBOX ni abrir un modo vivo por atajo.

La publicación robusta de pruebas usa intents, verificaciones SHA-256, intentos inmutables y `COMMITTED`, y debe distinguir éxito de transferencia de aprobación científica. Respetar la separación de permisos mínimos en NAS.

## 7. Qué se ha probado vs qué no

| Afirmación | Estado / evidencia |
|---|---|
| Código original global FFT recupera signos correctos con audio sintético | [CODE/CI] tests `test_legacy_audit.py` |
| Descubrimiento recursivo y recepción v2 | [CODE/CI] PR #4 y #7 |
| Pipeline sintético en Windows y Linux | [CI] PR #7: 296 PASS Windows, 295 PASS + 1 SKIP Ubuntu |
| Primitivas SMB bajo cuenta de servicio | [FIELD REPORT] 12 pruebas funcionales PASS; evidencia NAS histórica adicional |
| Copias autorizadas de vídeo real conservaron integridad SHA-256 | [FIELD REPORT] PASS |
| Vídeos del piloto controlado son visualmente reproducibles | [MANUAL] Sí, reportado por investigador |
| Offset correcto del piloto controlado juego 1 | **NO**: 0/7 ventanas; no estimado |
| Tres MP4 del piloto controlado generados y científicamente correctos | **NO** |
| Ausencia de errores de decodificación en todos los frames | **NO demostrado** |
| Búsqueda global FFT en rama experimental | [CODE/CI] Desarrollada, **desactivada por defecto**, CI Windows/Linux favorable; NO verificada con vídeos reales |
| Ejecución automática en vídeos reales y publicación NAS | **BLOQUEADA** |

## 8. Protocolo futuro de validación científica (no rellenar resultados a posteriori)

Para el **primer** par real solo, sobre copias locales y de manera expresamente autorizada:

1. Conservar rutas de origen, hashes, duración de pistas, FPS, codec y trazabilidad de sesión/juego.
2. Comprobar coincidencia de episodio mediante audio y/o eventos comunes; si no existe audio compartido, detener estimación automática o establecer una ruta de revisión humana.
3. Proponer offset con búsqueda amplia y criterios explícitos. Registrar candidatos alternativos, NCC, ratio de picos, número de ventanas, dispersión y mínimo solapamiento.
4. Comprobar que se recorta **la cámara correcta**; no reducir umbrales para hacer pasar un resultado.
5. Generar en scratch resultados de prueba, sin sobrescribir y sin publicar en `02_SYNCED`.
6. Revisar manualmente **inicio, mitad y final** del solapamiento, con al menos dos eventos identificables separados en el tiempo cuando sea posible. Inspeccionar labios/voz, movimientos y eventuales errores de decodificación. Registrar deriva temporal y tolerancia de QC **a definir científicamente**; no inventar un límite retrospectivo.
7. Solo después definir QC automatizable para todos, controles por muestra y revisión humana de casos de baja confianza.
8. Conservar referencias a informes, commit exacto, config de ejecución (sin secretos) y logs sanitizados. Un exit code 0 o `Published` **no implica** validación científica.

## 9. Errores concretos que NO repetir

- Tratar la **diferencia entre duraciones** de los archivos como desfase entre inicios.
- Decidir que AVI está «dañado» solo por mensajes aislados de H.264 o `Invalid sample_size`.
- Cambiar extensión AVI→MP4 sin remux real.
- Bajar umbrales de correlación para obtener cualquier resultado.
- Reutilizar el máximo global FFT antiguo **sin evidencia de confianza**.
- Recortar la cámara que comienza más tarde (bug de `sync_videos.sh`).
- Usar el fallback Python sin NumPy de `sync_research_project.sh`.
- Ejecutar Bash legado en carpetas actuales: puede abortar, sobrescribir, colocar resultados dentro de originales o confundir candidatos.
- Inferir juegos por `SNAP`, A/B, orden del explorador o fecha.
- Tratar `copy_successful` de JSON antiguos como entrega NAS completa.
- Ejecutar `pipeline_rg2019.py` clásico sobre 00_INBOX real: el mecanismo antiguo puede mover contenido a RAW.
- Equiparar 296 tests sintéticos con QC de una grabación real.
- Fusionar ramas o activar automatización antes de autorización científica y técnica.

## 10. Cómo reutilizar este trabajo para otro proyecto

Antes de adaptar a otra cohorte, cámara o protocolo, documentar explícitamente:

1. **Unidad científica:** sujeto, visita, sesión, juego, rol de cámara, versión del procedimiento.
2. **Evidencia de entrega:** manifiesto final externo, selección completa, SHA-256, renombrados, auxiliares y exclusiones.
3. **Propiedades reales de media:** codecs, contenedores, tiempos de audio/vídeo, duraciones, variabilidad de FPS, calidad de audio; no fiarse de extensiones.
4. **Modelo de sincronización:** fórmula y signo, rango de desfase esperado, si existe sonido común, deriva, interrupciones; definir qué cuenta como consenso y qué obliga a QC.
5. **Dos algoritmos complementarios:** búsqueda amplia de candidatos eficiente y comprobación local independiente y robusta, sin aceptación ciega.
6. **Seguridad:** originales inmutables, scratch suficiente, mínimo privilegio, publicación atómica/releíble, estados separados y reintentos controlados.
7. **Pruebas:** desfases positivos/negativos/cero, grandes, sin audio común, ruido, distintos niveles/duraciones, PCM/H.264 en AVI, timestamps erráticos, juegos múltiples, colisiones, errores de lectura, recuperación y concurrencia.
8. **QC humano previo a escala:** comparar inicio/medio/final con criterios documentados. Nunca dejar que un estado técnico promocione automáticamente resultados científicos.

## 11. Pendientes y próximos hitos

- **[CI / OPEN]** PR #9 en Draft, SHA `5cbd7ddad928d36b774476f0a34e28317fff5bc4`: 309 PASS Windows; 308 PASS + 1 SKIP Ubuntu. La revisión inicial del código no detectó regresión matemática reproducible; falta medir recursos reales y validar audio local sin activar el pipeline. Modo global sigue desactivado por defecto.
- **[FIELD REPORT / OPEN]** **PR #10 ya produjo los tres MP4 locales reales con el método de septiembre.** Ahora resta únicamente abrir la composición lateral existente y revisar sincronía de comienzo, mitad y final. No pedir palmadas ni anclas manuales; no repetir FFT ni pruebas de infraestructura.
- **[OPEN]** Caracterizar errores H.264 y timestamps que impacten realmente la salida, sin remux innecesario.
- **[FIELD REPORT / OPEN]** **Tres MP4 locales ya generados por Work;** falta exclusivamente la revisión científica visual/auditiva de comienzo, mitad y final, antes de cualquier `QCApproved`. La generación por sí sola no equivale a validación.
- **[OPEN]** Establecer tolerancia de desfase/deriva, tasas de fallos y criterios de aprobación.
- **[OPEN]** Adaptar límites de recursos para grabaciones reales, hacer ensayo end-to-end, definir carpetas con sesión/juego, permisos NAS y autorización explícita.
- **[OPEN]** Integrar generador `delivery.v2` con herramienta de copia de FURG cuando haya acceso.
- **[OPEN]** Emitir **README FINAL** con arquitectura y diagrama, procedimiento reproducible, parámetros justificados, matrices de pruebas reales, decisiones y rechazos, recuperación y guía de adaptación a otra investigación. Solo al completar los hitos anteriores (o documentar claramente excepciones aprobadas); nunca simular que ya está al 100 %.

## 12. Fuentes y referencias permanentes

- Original batch 02/09: https://github.com/chlmz/research-video-sync/blob/0d3eedf23f1b8c2b9314e475dbf5eca89787c06c/sync_research_project.sh
- Script de dos archivos 02/09: https://github.com/chlmz/research-video-sync/blob/e339d2d3e86dfe8a30bcd7b2cf3327fda68602e8/sync_videos.sh
- Auditoría de bugs: https://github.com/chlmz/research-video-sync/blob/a21279d6c7313d65eb1239e70f1bae3ae62b1420/docs/LEGACY_AUDIT.md
- Estimador actual: https://github.com/chlmz/research-video-sync/blob/a21279d6c7313d65eb1239e70f1bae3ae62b1420/rg2019/syncest.py
- Módulo FFmpeg: https://github.com/chlmz/research-video-sync/blob/a21279d6c7313d65eb1239e70f1bae3ae62b1420/rg2019/media.py
- Contrato de recepción: https://github.com/chlmz/research-video-sync/blob/a21279d6c7313d65eb1239e70f1bae3ae62b1420/docs/DELIVERY_V2.md
- Preproducción: https://github.com/chlmz/research-video-sync/blob/a21279d6c7313d65eb1239e70f1bae3ae62b1420/docs/PREPRODUCTION.md
- PR #4: https://github.com/chlmz/research-video-sync/pull/4
- PR #5: https://github.com/chlmz/research-video-sync/pull/5
- PR #6: https://github.com/chlmz/research-video-sync/pull/6
- PR #7: https://github.com/chlmz/research-video-sync/pull/7

**No subir a este README los archivos locales de pilotos, hashes identificables o logs brutos.** Sus informes se conservan en el entorno GPIS autorizado. Documentar únicamente resúmenes científicos y referencias internas no sensibles.

---

### Registro de revisiones

- **v0.9 · 2026-10-31** — El investigador reportó sincronía visual de los MP4 candidatos. Se aclaró que residen en scratch local del servidor y no en el NAS. QC formal/publicación siguen sin autorizarse.

- **v0.8 · 2026-10-31** — Work informó PASS técnico del adaptador de septiembre con los tres MP4 locales y hashes de copias intactos. Offset exacto y rutas reales permanecen privados; falta QC visual/auditivo, sin despliegue NAS.

- **v0.7 · 2026-10-31** — Se registró transcripción equivocada del SHA al delegar prueba local a Work; el preflight bloqueó correctamente. Se verificó el SHA actual de PR #10 y se autorizó el ensayo sin producción ni cambios en los originales.

- **v0.6 · 2026-10-31** — Decisión explícita: se descarta la palmada como requisito, se abandona el ajuste reiterado de umbrales; PR #10 con la ruta FFT NumPy de septiembre adaptada a sesiones/juegos profundos, 12 tests sintéticos PASS, tres MP4 locales pendientes de evaluación científica.

- **v0.5 · 2026-10-31** — Dos ensayos FFT globales reales realizados: el segundo, con ventanas más cortas, superó la puerta de solapamiento pero no la de similitud; sin offset validado, sin MP4 y QC NotApproved. Siguiente paso: evento audiovisual común, sin ajustar umbrales ni publicar métricas reales.

- **v0.4 · 2026-10-31** — Verificación autorizada de RAM/PCM del FFT global real: BLOCKED antes de cualquier cálculo; sin offset, sin MP4 nuevos. Se documenta decisión de priorizar memoria segura o diseño acotado, conservando cifras operativas reales en privado.

- **v0.3 · 2026-10-30** — PR #9 Draft creado; revisión CI exacta, memoria de ejemplo sintético y límites científicos documentados. Sin publicación de parámetros o duraciones de grabaciones reales.

- **v0.2 · 2026-10-30** — Registro de nueva rama experimental global FFT y saneamiento de datos sensibles de documentación pública.

- **v0.1 · 2026-10-30** — Bitácora inicial creada desde análisis de commits, scripts de septiembre, auditoría de legado, PR #4–#7, informes de validación de Windows/SMB y piloto piloto controlado. **No implica finalización ni sincronización correcta de piloto controlado.**
