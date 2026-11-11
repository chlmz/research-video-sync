# Instrucciones para Codex

Conserva las instrucciones y límites vigentes de `README.md` y de las guías aplicables a la rama de trabajo. Este archivo añade únicamente reglas para la respuesta final de Codex.

## Entrega al finalizar cada tarea

La respuesta final debe ser un resumen técnico autocontenido, comprensible sin abrir archivos locales, e incluir:

- **Qué y por qué:** resultado, cambios concretos y motivo; indica también si no hubo cambios.
- **Versión exacta:** repositorio `owner/repo`, rama y SHA completo del commit final o inspeccionado. Distingue cambios sin commit o sin publicar; no inventes un SHA.
- **Pruebas:** comandos o comprobaciones realmente ejecutados, entorno (sistema operativo, herramientas/versiones relevantes) y resultado `PASS` o `FAIL`; usa `SKIP` con motivo para lo no ejecutado. Incluye recuentos si existen. Separa ejecuciones de esta tarea de evidencia previa, y pruebas sintéticas, mocks o emulación de pruebas reales en el entorno objetivo; ninguna simulación demuestra validación real.
- **Riesgos y pendientes:** limitaciones, fallos, bloqueos, verificaciones faltantes y siguiente paso; aclara qué está propuesto, pendiente de revisión o efectivamente aplicado.
- **Evidencia GitHub:** enlaza el commit y PR, cuando existan; usa enlaces permanentes a archivos con `blob/<SHA>/...` y líneas, y a runs/jobs/artifacts por ID, indicando el SHA probado. No dependas exclusivamente de rutas `/workspace` u otros enlaces locales. Si la evidencia no está disponible en GitHub, dilo e incluye su contenido esencial saneado en la respuesta, sin inventar enlaces ni resultados.
- **Confidencialidad:** no expongas secretos, datos de participantes ni detalles internos en texto, logs, enlaces o metadatos. Este contrato no autoriza publicar evidencia privada en GitHub.

La entrega va en la respuesta. No crees ni actualices README, bitácoras u otros registros para cumplir estas reglas: esa labor corresponde al agente independiente de gobernanza documental. Tampoco crees agentes ni cambies automatizaciones o schedules por este contrato.
