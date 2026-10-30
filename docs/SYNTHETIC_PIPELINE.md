# Fase 2: ejecución exclusivamente sintética local

Base: `83addc7324562277e4a0aec69284aa8fd4273426`. Esta capa es independiente del
pipeline anterior y de su StateStore schema 1. No incorpora ninguna ruta NAS,
credencial o identidad científica. No está lista para producción.

## Contratos y módulos

`synthetic_plan.plan` descubre, conserva evidencia y calcula SHA-256 de los dos
inputs. Produce trabajos deterministas por participante/sesión/juego/fingerprint.
El fingerprint incluye el inventario completo (incluidos metadatos), rutas,
hashes y parámetros de sincronización/codificación. Un cambio invalida la
autorización; no se reutiliza un permiso para otros bytes o parámetros.

Cada trabajo contiene `sources`, evidencia de clasificación, estado `Blocked`
o `Authorized`, motivos de bloqueo y `qc_status: NotApproved`. La autorización
de pruebas requiere `synthetic_only`, `session_reviewed`, `delivery_complete`,
`integrity_verified`, fingerprint coincidente y evidencia no vacía. Tanto sesiones
configuradas como inferidas requieren revisión explícita. Un inventario con
errores, transferencias, manifiestos discrepantes o candidatos ambiguos bloquea
conservadoramente los trabajos del participante. Una autorización no elimina
esas incidencias. Este contrato es un fixture de pruebas, no una firma de un
responsable científico ni un control de acceso resistente a un usuario hostil.

`synthetic_local.Sandbox.create` exige una carpeta local nueva y crea únicamente
`input`, `scratch`, `published`, `state` y un marcador sintético. Rechaza rutas UNC,
enlaces y junctions. Todas las operaciones del ejecutor se limitan a esa raíz.
No usar esta API para declarar sintético un árbol científico existente.
`synthetic_run.run` es el punto de entrada autorizado: vuelve a planificar bajo
bloqueo y comprueba que el contrato sigue siendo válido. Las funciones de worker
y publicación son primitivas internas con precondiciones, no puntos de entrada
para ejecutar trabajos arbitrarios.

`synthetic_local.process` copia exclusivamente el par autorizado a una carpeta
UUID de scratch, verifica hashes en copia y original, exige espacio libre y
lanza `synthetic_worker` en otro proceso. El worker reutiliza sin modificaciones
`media.probe`, `extract_audio`, `encode`, `syncest.estimate_offset` y `trim_plan`.
Valida audio, vídeo y duración de ambas salidas y conserva el resultado científico
en `sync.json`. Cierra explícitamente los memory maps para Windows.

Límites de laboratorio: un juego a la vez por sandbox, 256 MiB de inputs por
defecto (máximo configurable 1 GiB), 120 s por vídeo, 1920×1080 a 60 fps,
sample rate entre 1 y 48 kHz. Scratch exige al menos 20 veces el tamaño de entrada
o 128 MiB. Worker: 120 s de plazo por defecto, configurable hasta 600 s.
Al vencer se termina el grupo de procesos POSIX o el árbol con `taskkill` en
Windows. El proceso hijo contiene también los bloqueos en FFmpeg. No es una
cuota estricta de memoria/disco; el uso de espacio debe monitorizarse antes de
admitir grabaciones largas. Los límites actuales son deliberadamente sintéticos.

`synthetic_publish` copia a staging dentro de `published`, comprueba hashes y
crea un manifiesto con tamaños, procedencia, parámetros y QC independiente.
Publica el directorio completo mediante rename entre hermanos del mismo volumen.
Un destino existente se valida completamente; los contenidos divergentes generan
conflicto sin sobrescritura. La repetición reconoce el mismo resultado.
Los staging y scratch fallidos se conservan como evidencia; no hay limpieza
automática ni borrado de originales.

`synthetic_run` guarda un journal separado con escritura temporal y reemplazo,
historial de 30 eventos, hasta 3 intentos por fingerprint y estado de procesamiento
independiente de QC. El bloqueo de sistema operativo se libera al morir el proceso;
no se roba un lock por antigüedad. Al reiniciar se verifica primero la publicación,
de modo que un fallo posterior al rename puede repararse sin recodificar.
Un reintento se solicita invocando `run` de nuevo; no hay servicio ni bucle diario.

## Ejemplo ejecutable y comprobaciones

En el checkout, con los requisitos de desarrollo y FFmpeg disponibles:

```bash
python3 examples/synthetic_demo.py --root /tmp/gpis-phase2-demo-new
python3 -m pytest tests/test_synthetic_pipeline.py -q
python3 -m pytest
```

La ruta del ejemplo debe ser nueva. Genera dos AVI de 40 s con señal determinista
y offset de 2 s. Ejecuta descubrimiento, autorización sintética, copiado, cálculo,
codificación y publicación. Inyecta una interrupción después de publicar y antes
de guardar el estado; recupera y repite. Exige `attempts: 1`, `recovered: true` y
`qc_status: NotApproved`. La ejecución realizada en `/tmp/gpis-phase2-demo`
produjo esos tres resultados. Los inputs originales permanecen idénticos.

Las pruebas incluyen gates faltantes, sesiones múltiples/inferidas, juegos
incompletos, duplicados, transferencias, manifiestos, cambios de inputs,
insuficiencia de espacio, copia corrupta, exclusión concurrente, reintentos
acotados, publicación interrumpida, conflicto y recuperación sin recodificación.
Los fallos SMB, sharing violations de Windows y PermissionError se simulan con
excepciones; el timeout se prueba bloqueando la extracción en un worker real,
con un marcador que demuestra que entró en esa fase antes de terminarlo.
El test end-to-end sí ejecuta FFmpeg y el estimador reales sobre
vídeo generado. No equivale a haber probado un servidor SMB o Windows real.

Resultados locales: Python 3.12.14, FFmpeg 7.1.5, Linux. Suite completa:
**195 passed** en 185,55 s, sin omisiones. Incluye los 172 tests previos y 23
nuevos. Después de reforzar el fixture del timeout se repitieron los 23 tests
de `test_synthetic_pipeline.py`; están incluidos en los 195, no se suman.
La advertencia de anyio sobre una API futura de pytest es externa al cambio.

CI: matriz Python 3.12 en Ubuntu 24.04 y Windows 2022, FFmpeg instalado en cada
runner. Se aceptan PR dirigidos a `main` y a `feature/gpis-recursive-discovery`.
Solo eventos PR o ejecución manual; no se duplica por push+PR y se cancela una
ejecución anterior de la misma referencia. Se comprueban Python 3.12, FFprobe y
codificación H.264/AAC con FFmpeg antes de ejecutar todos los tests. JUnit queda
como artefacto y sus conteos/fallos sintéticos aparecen en el resumen de Actions.
Las versiones FFmpeg de CI no están fijadas a 9.

La ejecución de diagnóstico 41109342590 confirmó en Ubuntu 195 tests sin fallos
ni omisiones. Windows ejecutó 195 con 13 fallos y 0 omisiones. Se corrigieron
lecturas de scripts UTF-8 que dependían del encoding CP1252 y el fixture de
duplicados por mayúsculas: ahora crea los dos candidatos en subdirectorios
distintos de la misma sesión, para que no se sobrescriban en NTFS. Las aserciones
se conservan. El estado de validación posterior debe comprobarse en los checks
del PR #5; un fallo del runner no equivale automáticamente a un fallo científico.

## Límites y decisiones científicas

El marcador no demuestra que un vídeo sea sintético. El operador debe usar
exclusivamente el generador y fixtures; no copiar material científico a la raíz.
Los controles de rutas y locks asumen un sandbox local confiable, sin procesos
externos sustituyendo enlaces concurrentemente. No son una barrera contra un
atacante con escritura en el mismo directorio.

Rename y locks se han diseñado para disco local y escritores cooperantes. No
se garantizan atomicidad/durabilidad frente a corte de energía, clientes externos
ni equivalencia de rename/locks en SMB. La existencia de staging es recuperable,
pero no se reutiliza a ciegas: se vuelve a procesar si no existe publicación válida.
Si los originales cambiaron desde la aprobación, la reanudación bloquea.

Antes de cualquier uso científico se necesita decisión del responsable sobre:
límites de sesión y juegos sin número; evidencia aceptable de entrega completa;
quién verifica integridad y cómo registra aprobación; criterios y responsable
de QC científico. `TechnicalSuccess`/`Published` nunca implican `QCApproved`.
La autorización de pruebas debe sustituirse por un contrato científico revisado
antes de integrar datos reales. El estimador matemático permanece intacto.

## Validación posterior con Work en GPIS-SERVER

Estos pasos son para una tarea posterior explícita, solo con fixtures locales:

1. Obtener este checkout/commits en un directorio de desarrollo separado. No
   modificar el checkout operativo ni configurar tareas programadas.
2. Comprobar `py -3.12 --version`, `ffmpeg -version`, `ffprobe -version` y espacio
   libre en scratch. No cambiar cuentas, ACL ni rutas de configuración científicas.
3. En un entorno Python de desarrollo con `requirements-dev.txt` disponible,
   ejecutar `py -3.12 -m pytest tests/test_synthetic_pipeline.py -q` y después
   `py -3.12 -m pytest`. Registrar versiones y resultados, incluyendo skips.
4. Ejecutar desde el checkout:
   `py -3.12 examples/synthetic_demo.py --root C:\GPIS\temp\synthetic-phase2-new`.
   Exigir carpeta inexistente y verificar `recovered: true`, `attempts: 1`,
   QC `NotApproved`, dos MP4 y hashes del manifiesto. No apuntar al NAS.
5. Probar separadamente semántica Windows de archivos abiertos, finalización del
   árbol de FFmpeg y liberación del lock tras matar el proceso. El test automatizado
   de PermissionError es una simulación, no prueba de esas semánticas reales.
6. Conservar logs sintéticos y presentar evidencia para revisión. Cualquier prueba
   posterior sobre SMB, identidades o publicación científica requiere un alcance
   específico y las autorizaciones de escritura correspondientes; no está incluida.
