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
- [FIELD REPORT] En Dell Windows 11, suite de regresión 264 PASS, 0 FAIL, 2 SKIP reportados; prueba funcional SMB posterior 11 controles PASS bajo `gpis_runner` sin elevación. La observación de identidad SMB histórica se corroboró por registros NAS del 29/10; no debe presentarse como identidad independiente registrada para **la misma** sesión SMB del 30/10.
- **PR #7** `codex/gpis-delivery-v2`, head `a21279d6c7313d65eb1239e70f1bae3ae62b1420`: manifiesto de recepción `rg2019.delivery.v2`, UUID de sesión independiente, SHA-256, materiales auxiliares, exclusiones trazadas y juego 1 inferido solo para par único en sesión revisada. [CI] Windows: 296 PASS / 0 FAIL; Ubuntu: 295 PASS / 1 SKIP. Son pruebas sintéticas, no validación con vídeos reales.
- Documentos base: `docs/PREPRODUCTION.md`, `docs/DELIVERY_V2.md`, `docs/STORAGE_PERMISSIONS.md`.
- Todos los PR anteriores permanecían en borrador en la evaluación original. No asumir despliegue ni merge por la existencia de ramas.

### 2026-10-30 — primer piloto real controlado (P3, juego 1)

**[FIELD REPORT]** Un par explícitamente rotulado madre1/niño1 fue copiado de manera autorizada al scratch del Dell. SHA-256 de original y copia, tamaño y mtime fueron verificados sin alterar los originales. La prueba se hizo con el código del commit `a21279d6...`, sin cambiar sus parámetros.

**Metadatos declarados por FFprobe/FFplay:** AVI, vídeo H.264 Main (FourCC H264), 1280×720, 30 FPS; audio PCM `pcm_s16le` mono a 16 kHz. Duraciones de contenedor reportadas: madre **378.867 s** y niño **220.800 s**. Diferencia de duraciones: **158.067 s**; **NO** confundirla con el offset real entre inicios de grabación. Cabeceras/timestamps deben verificarse.

**Resultado del estimador de audio:** extracción completa de audio posible, pero **0 de 7 ventanas válidas**, NCC mediana **0.0207**, confianza **0.0**; no se aceptó offset, no se hizo etapa fina ni se generaron MP4 sincronizados.

**Decodificación visual:** se reportaron errores H.264 («No start code is found» / «Error splitting the input into NAL units»). FFplay logró abrir y avanzar por el AVI; mostró advertencia `Invalid sample_size -1 at stream 1 setting it to 0`. [MANUAL] El responsable inspeccionó visualmente ambos vídeos y los consideró bien grabados y reproducibles. Esta apreciación **no sustituye** escaneo integral de errores ni validación de timestamps.

**Decisión:** NO cambiar únicamente `.avi` por `.mp4`, NO recodificar originales por rutina, NO bajar umbrales de NCC, NO inventar un offset. Conservar las copias y audios de diagnóstico locales, sin subirlos a GitHub ni a servicios externos. QC continúa `NotApproved`.

**[HYPOTHESIS]** La búsqueda limitada a ±120 s puede omitir un offset real mayor; el original de septiembre buscaba globalmente. **La diferencia de duración de ~158 s no demuestra ese offset.** Alternativamente, puede no haber audio compartido suficiente o puede estar mal emparejada la sesión. Se requiere evidencia, no inferencia.

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
- En la prueba real P3 no avanzó a la segunda etapa.

**[OPEN — implementación por Codex]** Recuperar la capacidad de búsqueda global FFT como **generador de candidatos** dentro de Python, seguida de verificación multicapa por ventanas, memoria acotada y rechazo de coincidencias espurias. No declarar esta integración implementada hasta disponer de SHA/PR/CI y réplica en Dell.

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

Una auditoría de solo lectura encontró **3 participantes**, **8 AVI**, **20 INSV**, **20 LRV** y **6 JSON históricos**. Los seis JSON contienen 13 referencias AVI para los ocho AVI observados, con rutas/nombres renombrados y cinco referencias sin correspondencia por tamaño. Ningún indicador `copy_successful` prueba la llegada completa al NAS.

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
GPIS-SERVER (gpis_runner) → copia verificada a scratch local
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

`01_RAW` debe permanecer inmutable. No inferir que `CAMERAS_PC` tiene permisos seguros: la herencia de permisos de escritura detectada en RAW y pilotos requiere corrección aprobada. Ningún experimento de sincronización debe modificar ACL, mover INBOX ni abrir un modo vivo por atajo.

La publicación robusta de pruebas usa intents, verificaciones SHA-256, intentos inmutables y `COMMITTED`, y debe distinguir éxito de transferencia de aprobación científica. Respetar la separación de permisos mínimos en NAS.

## 7. Qué se ha probado vs qué no

| Afirmación | Estado / evidencia |
|---|---|
| Código original global FFT recupera signos correctos con audio sintético | [CODE/CI] tests `test_legacy_audit.py` |
| Descubrimiento recursivo y recepción v2 | [CODE/CI] PR #4 y #7 |
| Pipeline sintético en Windows y Linux | [CI] PR #7: 296 PASS Windows, 295 PASS + 1 SKIP Ubuntu |
| Primitivas SMB bajo cuenta de servicio | [FIELD REPORT] 11 pruebas funcionales PASS; evidencia NAS histórica adicional |
| Vídeos P3 archivados llegaron al Dell sin cambio SHA | [FIELD REPORT] PASS |
| Vídeos P3 son visualmente reproducibles | [MANUAL] Sí, reportado por investigador |
| Offset correcto del piloto P3 juego 1 | **NO**: 0/7 ventanas; no estimado |
| Tres MP4 P3 generados y científicamente correctos | **NO** |
| Ausencia de errores de decodificación en todos los frames | **NO demostrado** |
| Uso de búsqueda global FFT segura en rama actual | **PENDIENTE** |
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

- **[OPEN]** Obtener del Codex el SHA/PR de la **búsqueda FFT global como candidato + validación por ventanas** y comprobar matemáticamente signo, memoria y comportamiento con audio no relacionado.
- **[OPEN]** Ejecutar ese estimador con los WAV existentes del piloto P3 en el Dell, sin cambiar originales, y conservar métricas. Si no hay coincidencia acústica, resolver científicamente el emparejamiento.
- **[OPEN]** Caracterizar errores H.264 y timestamps que impacten realmente la salida, sin remux innecesario.
- **[OPEN]** Generar dos MP4 y side-by-side locales y registrar QC manual de inicio, medio y final. **No declarar hecho aún.**
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

- **v0.1 · 2026-10-30** — Bitácora inicial creada desde análisis de commits, scripts de septiembre, auditoría de legado, PR #4–#7, informes de validación de Windows/SMB y piloto P3. **No implica finalización ni sincronización correcta de P3.**
