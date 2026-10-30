# Detector de entregas RG2019 (experimental, sin procesamiento)

Implementado sobre `a6b2a393230bbe5a08624be781897abff8b2505e`.
El punto de entrada es `discover_rg2019.py`, que imprime JSON en stdout.
No llama a FFmpeg, no calcula offsets, no mueve archivos ni escribe estado en NAS.
`find_sources` y el pipeline anterior conservan su comportamiento. El detector
recursivo se ofrece como `rg2019.discovery.discover_field` para una integración
posterior explícita. No está listo para producción.

## Configuración y ejecución

Ejemplo para un árbol **sintético local**; guardar fuera de las carpetas científicas:

```json
{
  "followup_root": "C:\\GPIS\\temp\\synthetic_followup",
  "field_participant_id_regex": "^\\d{6}$",
  "field_sessions": {
    "001234": ["entrega_A/sesion_A", "entrega_A/sesion_B"]
  }
}
```

```text
python discover_rg2019.py --config config.json --participant 001234
```

Los IDs son cadenas: se conservan los ceros iniciales. `field_sessions` contiene
raíces relativas al participante, con `/` como separador incluso en Windows.
Cada raíz delimita una sesión revisada y puede contener ramas separadas por cámara,
fechas y niveles repetidos. No se permiten raíces superpuestas. `.` identifica
todo el participante como una sola sesión **solo si esa delimitación está
demostrada**. Si no hay raíces declaradas, el detector puede usar las carpetas
inmediatas bajo el participante como particiones provisionales **solo** si todos
los AVI están dentro de ellas, cada partición contiene AVI con ambos roles, no
hay roles/juegos contradictorios ni errores de lectura, enlaces excluidos o
archivos de transferencia. Si falta alguna condición, emite
`REVIEW_SESSION_UNSPECIFIED` y no construye pares. Por ejemplo, `CAM1/mother1.avi`
y `CAM2/children1.avi` no se convierten en sesiones ni en un par. El origen
automático es evidencia de partición, no prueba de que sea una entrega completa:
se mantiene `WaitingForDelivery`. Las raíces explícitas permiten resolver casos
que requieren revisión científica. Los archivos fuera de ellas quedan pendientes.
No se infieren sesiones de fechas, nombres CAMERA ni JSON de copia.
La clave `session_id` es la ruta de la partición completa.
`session_origin` distingue `inferred_top_level` de `configured`, para que la
revisión humana pueda evaluar cómo se obtuvo cada límite.

Código de salida 0 significa inventario sin incidencias de clasificación; 2 indica
revisión. Ninguno autoriza procesamiento ni demuestra entrega completa.

## Clasificación conservadora

- Solo AVI son candidatos científicos en este detector. INSV/LRV son
  `Auxiliary360`; JSON son `AuxiliaryManifest`; el resto se conserva como `Other`.
- Se reconocen tokens completos `mother/mom` y `children/child`, sin distinguir
  mayúsculas, en el nombre y componentes bajo la raíz de sesión.
- Un número de 1–99 unido inmediatamente al rol (`mother1`, `children2`) aporta
  evidencia de juego. No se usan números separados (`mother_1`), fechas, códigos
  de cámara o índices de grabación. Estos casos requieren revisión. No hay
  asignación implícita de juego 1.
- Roles o juegos contradictorios, posibles errores tipográficos y candidatos
  adicionales impiden escoger un par. La sugerencia no modifica el nombre.
- Los nombres AVI repetidos, incluso con distinto uso de mayúsculas, quedan en
  revisión cuando pertenecen a la misma sesión. Son legítimos entre sesiones
  independientes. Si la sesión aún no está determinada, se mantiene la alerta
  porque la relación entre los archivos no está resuelta.
- Enlaces simbólicos, junctions/reparse points de Windows y archivos especiales
  se excluyen y se notifican. Errores de lectura se conservan como incidencias;
  no equivalen a un inventario completo. La comprobación no constituye una
  instantánea atómica de una entrega que continúa cambiando.

Cada archivo conserva ruta relativa, nombre original, tamaño, mtime en nanosegundos,
tipo de material, sesión, rol, juego, tokens observados y códigos de revisión.
No se inventan metadatos audiovisuales ni hashes que no se hayan medido.

## Estado y manifiestos

El documento de descubrimiento tiene `schema: 2` y contiene participante,
inventario, sesiones y juegos. El estado de cada juego es `CandidatePair` o
`NeedsReview`; un juego sin número conserva `game: null` y
`REVIEW_GAME_UNSPECIFIED`.

Las dimensiones restantes son independientes:

| Dimensión | Resultado del detector | Puerta pendiente |
| --- | --- | --- |
| Entrega | `WaitingForDelivery` | Demostrar completitud |
| Manifiesto | `NotChecked`, `InventoryMatches`, `ManifestMismatch` | Reconciliar registros de copia |
| Integridad | `NotVerified` | `IntegrityVerified` después de verificación autorizada |
| QC científico | `NotApproved` | `QCApproved` mediante revisión científica |

`CandidatePair` puede coexistir con `ManifestMismatch` y `WaitingForDelivery`.
Nunca debe usarse aisladamente como autorización de procesamiento.

No se conoce el esquema de los seis JSON reales. Se conservan como auxiliares y
se emite `REVIEW_MANIFEST_SCHEMA`. El único contrato comparable implementado es
explícito y acotado a 1 MiB:

```json
{
  "schema": "rg2019.inventory.v1",
  "files": [
    {"relative_path": "CAM1/mother1.avi", "size": 123},
    {"relative_path": "CAM2/children1.avi", "size": 456}
  ]
}
```

Las rutas son relativas a la sesión y la lista declara todos sus AVI. Diferencias
de rutas o tamaños producen `ManifestMismatch`; coincidencia no demuestra hashes,
completitud de entrega ni integridad. Registros desconocidos, inválidos o excesivos
requieren revisión; nunca se selecciona un esquema por conjetura.

`migrate_field_state` realiza una migración pura e idempotente desde schema 1:
guarda el registro completo en `legacy_state`, crea sesión y juego sin identificar
y exige revisión. No convierte `SUCCESS` anterior en `QCApproved`. No modifica el
objeto original ni escribe archivos. `StateStore` sigue usando schema 1 para que
el pipeline anterior no interprete inventarios nuevos como trabajo procesable.
No sustituir sus archivos por documentos schema 2.

## Validación sintética de esta implementación

- `python3 -m pytest`: 172 tests pasaron en 239,64 s (139 existentes y 33 del
  detector). El último cambio de trazabilidad, `session_origin`, se comprobó
  inmediatamente después con `python3 -m pytest tests/test_field_discovery.py -q`:
  33 tests pasaron en 0,51 s. Estos 33 están contenidos en los 172; no se suman.
- `git diff --check`: sin errores. Una advertencia externa de compatibilidad
  futura entre anyio y pytest; no hubo tests omitidos.
- Solo fixtures sintéticos; no se accedió al NAS ni se procesaron vídeos reales.

Para esta revisión se añadieron casos de particiones automáticas conservadoras,
carpetas CAMERA separadas, entregas incompletas y duplicados dentro/entre sesiones.
La suite completa se ejecuta en CI con Python 3.12 y FFmpeg en Ubuntu 24.04 mediante
`.github/workflows/tests.yml`. Los resultados de esa ejecución deben consultarse
en el PR; el resultado local actual se comunica en la entrega de esta revisión.

## Integración pendiente

1. Validar científicamente las raíces de sesión, juegos sin número, duplicados,
   nomenclaturas y discrepancias de los JSON de copia; implementar adaptadores
   solo tras documentar esos esquemas. Ninguna entrega real está demostrada completa.
2. Conectar al procesamiento con puertas explícitas de completitud, verificación
   de integridad y aprobación QC, preservando rutas y usando claves de salida por
   participante/sesión/juego. Diseñar persistencia separada, reintentos y revisión
   de las migraciones. No reutilizar automáticamente la promoción INBOX→RAW actual.
3. Para publicación NAS, obtener autorización de escritura en 02_SYNCED y
   99_LOGS_QC y validar publicación temporal/atómica, conflictos y recuperación.
   Esta implementación no cambia ACL, identidades ni carpetas NAS.
4. Probar, en una tarea autorizada posterior, lectura con `gpis_runner` y la
   identidad NAS `gpis_server`, y compatibilidad Windows 11/Python 3.12/FFmpeg 9.
   Validación aquí: Linux, Python 3.12 y FFmpeg 7.1.5, solo datos sintéticos.
5. Antes de ejecución diaria: validar scratch C:\GPIS\temp, espacio, bloqueos,
   credenciales, logs y condiciones de reanudación; después autorizar por separado
   la tarea programada. No se ha activado ninguna automatización.
