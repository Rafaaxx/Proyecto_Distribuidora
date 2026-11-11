# ADR-073 — Aceptación y endurecimiento: tareas diarias con rol propio, aviso de consistencia, encabezados y CSP, matriz de permisos y suite de Playwright

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-11-11 |
| Referenciado en | `openspec/changes/28-aceptacion-y-endurecimiento/design.md` D0 a D17 y sus specs delta; `00-vision-y-alcance.md` §9; `01-dominio.md` §20, AUD-02; `02-arquitectura.md` §7.6, §15, §16, §18; `04-roadmap-changes.md` §12; ADR-015, ADR-018, ADR-020, ADR-039, ADR-051, ADR-057, ADR-071, ADR-072 |

**Change 28. Gobernanza: dominio ALTO/CRÍTICO (permisos de base, rol que borra, encabezados de seguridad). CRÍTICAS: D3, D10. ALTAS: D2, D5, D8, D9, D11. **Decisiones D0 a D17 aprobadas por el usuario el 2026-11-10, todas con la opción A (texto de ayuda de D17 incluido); Q2 resuelta con un permiso nuevo. Vigente desde el 2026-11-11, al archivar el change 28.**

## Contexto

La fila 28 de `04` §12 cierra la etapa 1: suite Playwright con los 12 criterios de `00` §9, verificación diaria de consistencia (`02` §7.6, ADR-015, ADR-039), encabezados de seguridad y CSP (`02` §18, ADR-071 punto 3), revisión de permisos de base y limpieza de `intento_login` de más de 24 horas con un rol distinto de `app_runtime` (ADR-018, ADR-057 punto 9). Al proponer se relevó: Playwright sin instalar; verificación solo como consulta; Caddy solo con HSTS; sin limpieza; la CI sin `tests/concurrency`; el ratchet de INV-21 con 174 de 174 rutas declaradas pero sin comprobar que sus pruebas existan.

## Decisión (opciones A de `design.md`, aprobadas el 2026-11-10)

1. **Alcance (D0).** Un change en ocho lotes, excepción de tamaño.
2. **Deuda del 14 (D1).** Se incluye el motivo en la auditoría de `COMPRA_ANULAR` y `PAGO_PROVEEDOR_ANULAR` (AUD-02); la consulta de auditoría con motivo y el mecanismo común de puertos de `catalogo` pasan a la etapa 2.
3. **Tareas (D2, D6, D7).** Servicio `tareas` (imagen del backend, red `datos`, sin puertos) que todos los días a `TAREAS_HORA` (05:00) verifica la consistencia de cada organización y borra `intento_login` de más de 24 horas; orden a pedido `tareas ahora`; salud por archivo de estado.
4. **Rol (D3, CRÍTICA).** `app_mantenimiento`: `SELECT` de saldos y libros, `INSERT, SELECT` de `verificacion_consistencia`, `SELECT, DELETE` de `intento_login`. Se crea por script de inicialización o por el runbook antes de migrar; la migración otorga los permisos y falla si el rol no existe.
5. **Verificación (D4).** `saldo_cuenta`, `stock_saldo`, `stock_total` y promedio vigente contra el último `costo_producto_mov`; nunca corrige.
6. **Aviso (D5, D17).** Tabla `verificacion_consistencia`; aviso en `/admin` para quien tenga el permiso nuevo `VER_CONSISTENCIA` (solo lectura; `Administrador` y `Administración`, Q2) con su «(?)»; `Administración` no recibe `ADMIN_CONFIGURACION`; catálogo de 41 permisos; log crítico; salud no sana; aviso externo opcional (`AVISO_TAREAS_URL`, precisión del apply). La escritura no pasa por el bus (no es operación de negocio).
7. **Encabezados (D8, D9).** En Caddy, fragmento compartido con el perfil `lan`; CSP aplicada directamente, sin `unsafe-eval` ni `unsafe-inline`; documentación de la API apagada en producción.
8. **Permisos (D10, CRÍTICA).** Matriz explícita por rol y tabla con justificación de cada `DELETE`, verificada contra la base; atributos de roles, dueños y `PUBLIC`.
9. **Cobertura (D11, D12).** La cobertura de INV-21 asocia cada ruta con sus pruebas y el ratchet comprueba que existan y citen INV-21; ratchet de invariantes de la etapa 1; `tests/concurrency` en la CI.
10. **Aceptación (D13 a D16).** Playwright contra el compose de producción en el proyecto `distribuidora-aceptacion`; siembra del escenario de aceptación con los nombres de usuario de desarrollo y una segunda organización; suite en serie, proyectos «PC» y «teléfono», solo Chromium; criterio 7 con espía de compartir; criterio 12 cubierto por las pruebas de restauración del 27b; job en push a `main`.

## Precisiones del apply

Dentro de las opciones aprobadas; ninguna cambia una decisión.

- **Rol (D3).** `app_mantenimiento` se crea con `30-init-mantenimiento-role.sh` en un volumen nuevo; en un entorno existente hay que crearlo **antes** de migrar (runbook C12). Variable nueva `APP_MANTENIMIENTO_DB_PASSWORD` (sexto secreto, con `:?` en el compose).
- **Aviso externo de tareas (D2, D5; ampliación aprobada el 2026-11-11, opción A).** *Contexto:* el primer apply dejó a `tareas` solo en la red `datos` (`internal`, sin internet), así que no podía avisar por correo y dependía de que alguien mirara `dc ps` o `/admin`; si el servicio se caía o el equipo se apagaba, nadie se enteraba. *Opción elegida (A):* `tareas` se conecta también a la red `salida` (la de `copia-externa`: tiene internet pero no ve ni Postgres ni el backend; sin puertos publicados) y llama a un servicio de «hombre muerto» tipo healthchecks.io. La base, el backend y la red `datos` (`internal`) quedan igual. *Opción descartada (B):* un servicio avisador aparte, sin acceso a la base, que lea el estado de `tareas` y avise; evitaba tocar las redes de `tareas` pero agregaba un servicio, un volumen compartido y otra pieza que puede fallar sin avisar. *Por qué A:* `salida` solo se usa para salir (nada entra a `tareas`), el rol `app_mantenimiento` sigue limitado (sin secretos extra) y no se abre ningún puerto. *Comportamiento:* tras cada corrida (programada o `ahora`), sin diferencias y sin fallos llama a `AVISO_TAREAS_URL`; con diferencias o fallo, a `AVISO_TAREAS_URL/fail`; sin la variable no hace nada. Espera de 10 s y 3 intentos; un aviso que no llega **nunca** cambia el resultado ni la salud de la corrida y solo queda en el log, sin la dirección (es secreta). Nunca envía datos del negocio. *Variable propia:* `AVISO_TAREAS_URL`, distinta de `AVISO_URL` (la de `copia-externa`), para que cada control de healthchecks.io sea independiente (período de 1 día y gracia de unas 2 horas para «Verificación diaria»). Procedimiento: runbook C13.
- **Permiso `VER_CONSISTENCIA` (Q2).** También lo recibe `Administración`. El endpoint `GET /api/v1/sistema/consistencia` está en el módulo `reportes` (por los límites de import-linter). Aviso en el inicio de `/admin`. **Limitación:** un rol a medida con `VER_CONSISTENCIA` y sin `REVISAR_OBSERVACIONES` no ve el aviso; fuera de alcance.
- **Motivo en la auditoría (D1).** Los handlers de `COMPRA_ANULAR` y `PAGO_PROVEEDOR_ANULAR` devuelven `DatosDeAuditoria(motivo_id=...)`.
- **Encabezados (D8, D9).** `infra/caddy/encabezados.caddy`; la CSP se aplicó sin relajar. Zod 4 sondea `new Function` y la CSP lo informaba como violación: se resolvió en la app con `src/lib/zodSinEval.ts` (`jitless`). `/docs`, `/redoc` y `/openapi.json` apagados en producción.
- **Cobertura (D11, D12).** Ratchet de INV-21 de ruta a pruebas (`archivo::nombre`); ratchet de invariantes de la etapa 1; `tests/concurrency` en un paso propio de la CI. En esta máquina la concurrencia se corre por tandas (600 passed en 6 tandas).
- **Aceptación (D13 a D16).** `seed --escenario-aceptacion`; Playwright 1.64.1 solo Chromium; 41 de 41 pruebas en dos corridas. Importar y publicar listas lo hace `admin` (`IMPORTAR_DATOS`, `PUBLICAR_LISTAS` son solo de `Administrador`, `01` §19). El criterio 9 lo anula un supervisor (`sup01`) desde `/admin` (`ANULAR_VENTA` y `LIBERAR_UBICACION`, VTA-21). El criterio 4 carga todo el stock del criterio 5 (STK-09). El tramo 5 a 8 es un único teléfono sin señal (jornada por usuario y dispositivo, ADR-005). Playwright usa `--ignore-certificate-errors` para registrar el service worker con el certificado interno de Caddy. En el compose de producción `FRENTE_SUBRED` y los puertos de Caddy son variables. «Acción no permitida»: la suite cubre solo la API (403); las pantallas son un paso manual (tarea 9.1).

## Resultados de la prueba manual 9.1 (2026-11-11)

Hecha por el usuario con los usuarios de desarrollo; el detalle está en `design.md` del change. En resumen: encabezados correctos en la PC; PWA instalada y nota de venta generada y compartida en el teléfono real (el teléfono no llegaba a la PC por el firewall de Windows; se resolvió con una regla de entrada TCP 80/443); `tareas ahora` sin diferencias en desarrollo y, con un saldo alterado a mano en aceptación, una diferencia informada, aviso en `/admin` para `admin` y no para `vendedor`; limpieza de 134 intentos de más de 24 horas con los recientes y la auditoría intactos; `npm run test:e2e` con 41 pruebas en verde; `vendedor` sin acceso a las pantallas de administración; control de healthchecks rojo con diferencias y verde sin ellas; criterios 4 a 8 en el teléfono real con modo avión, todo OK. **Hallazgo:** un navegador con un dispositivo revocado guardado recibe el 401 genérico; se resuelve borrando los datos del sitio. **Ajuste posterior:** el informe de `tareas ahora` usa el singular («1 diferencia», «1 intento… borrado»). **Pendiente (e):** la instalación en la PC de la oficina (crear el rol antes de migrar, actualizar, comprobar `tareas` sano, crear un control de healthchecks propio, distinto del de pruebas).

## Consecuencias

- Un secreto nuevo (`APP_MANTENIMIENTO_DB_PASSWORD`) y un paso nuevo en la actualización de un entorno existente (crear el rol antes de migrar).
- `tareas` avisa por correo mediante un servicio externo (`AVISO_TAREAS_URL`, opcional): queda en la red `salida` además de `datos`. Sin esa variable sigue dependiendo de la revisión semanal de `dc ps` y del aviso en `/admin`. Un control más que crear en healthchecks.io (cuenta gratuita del dueño).
- `app_runtime` sigue sin `DELETE` en libros e `intento_login` (INV-05).
- Una diferencia de saldos se ve en `/admin` al día siguiente sin depender de mirar Docker.
- Safari del iPhone y el envío real por WhatsApp quedan en la prueba manual.

## Alternativas consideradas

Ver `design.md` (D2 B/C, D3 B/C, D5 B/C, D8 B/C, D9 B, D11 B/C, D13 B/C, D14 B).
