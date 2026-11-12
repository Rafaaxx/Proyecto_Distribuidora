# Propuesta de cambios a `docs/` — change 21 `pwa-y-bootstrap`

> **Propuesta completa (tarea 19.1) con lo aprobado en 0.1 (opción A en todas, salvo D14 = B; bloqueo del PIN en 10 fallos) y las precisiones del apply. Se aplica a `docs/` al archivar el change, con el visto bueno del usuario; hasta entonces `docs/` no cambia.** Cada sección tiene el **texto actual** (copiado de `docs/` tal como está hoy) y el **texto propuesto**. Las decisiones van en `docs/adr/ADR-062-pwa-bootstrap-y-sesion-local.md` (*Propuesto*).
>
> Orden: `01` §4, §8.2, §13, §14; `02` §7.1, §11, §12.3, §13.1 a §13.5; `04` §11.

---

## `01-dominio.md`

### §8.2 — RUT-03

**Texto actual**

> | RUT-03 | La apertura requiere conexión y `ABRIR_JORNADA`. Toma la ubicación para el usuario y el dispositivo de la sesión. El bootstrap lo ejecuta el cliente después de abrir (change 21). | 1 |

**Texto propuesto**

> | RUT-03 | La apertura requiere conexión y `ABRIR_JORNADA`. Toma la ubicación para el usuario y el dispositivo de la sesión. El cliente ejecuta el bootstrap después de abrir, al iniciar sesión o desbloquear con conexión si no tiene los datos de la jornada abierta, y cuando el usuario actualiza los datos. El bootstrap exige una jornada `ABIERTA` propia en el dispositivo (`JORNADA_REQUERIDA`) (ADR-062). | 1 |

### §13 — SYN-11

**Texto actual**

> | SYN-11 | El bootstrap incluye: productos y presentaciones activos, clientes con saldo y datos de crédito, versiones de lista vigentes y las anteriores permitidas, reglas de descuento activas, stock de la ubicación tomada, permisos y topes del usuario, credenciales de autorización de supervisores y configuración de la organización. No incluye costos ni utilidades salvo que el usuario tenga `VER_COSTOS`. | 1 |

**Texto propuesto**

> | SYN-11 | El bootstrap incluye: productos y presentaciones activos, clientes activos y suspendidos (y el consumidor final) con la cartera del usuario, saldo y datos de crédito, versiones de lista vigentes, programadas y las anteriores permitidas (estas, solo con `USAR_LISTA_ANTERIOR`), reglas de descuento activas no vencidas, stock de la ubicación tomada, permisos, contexto de venta y topes del usuario, medios, motivos y alícuotas activos, credenciales de autorización de supervisores (solo con `VENDER`), numeración del dispositivo y configuración de la organización y de la nota. Se lee en una sola foto de la base. No incluye costos ni utilidades (ADR-062). | 1 |

### §14 — SEG-03 y SEG-04

**Texto actual**

> | SEG-03 | Con conexión, cada usuario define un PIN para el dispositivo. Sin conexión, el PIN desbloquea la sesión local. | 1 |
> | SEG-04 | Superados los intentos fallidos configurados, la sesión local se bloquea y requiere inicio de sesión con conexión. Las operaciones pendientes no se pierden. | 1 |

**Texto propuesto**

> | SEG-03 | Con conexión, cada usuario define un PIN de 6 dígitos para el dispositivo, que no puede ser trivial. Se pide al abrir la aplicación, con o sin conexión; no se pide al volver de segundo plano. Una sola sesión local por dispositivo: cerrar sesión o iniciar con otro usuario borra la sesión, el PIN y los datos maestros del anterior (ADR-062). | 1 |
> | SEG-04 | Superados 10 intentos fallidos del PIN de desbloqueo (constante del código, no un parámetro), la sesión local se bloquea, se borra la derivación del PIN y se requiere inicio de sesión con conexión. Las operaciones pendientes no se pierden. | 1 |

---

### §4 (parámetros) — fila "Intentos fallidos de PIN antes de bloquear" (línea ~101)

**Texto actual**

> | Intentos fallidos de PIN antes de bloquear | Número | 5; vale para el PIN de desbloqueo local y, con conexión, para los fallos de un mismo usuario contra el PIN de un mismo supervisor (`intentos_pin_max`). El tope general por supervisor (20 fallos de cualquier usuario) es una constante del código, no un parámetro (ADR-055) | 1 |

**Texto propuesto**

> | Intentos fallidos de PIN antes de bloquear | Número | 5; vale solo para los fallos de un mismo usuario contra el PIN de un mismo supervisor, con conexión (`intentos_pin_max`). El tope general por supervisor (20 fallos de cualquier usuario, ADR-055) y el bloqueo del PIN de desbloqueo local (10 fallos, ADR-062) son constantes del código, no parámetros | 1 |

Sin cambios necesarios (verificado, tratan solo la verificación en línea del PIN de un supervisor): `01` §SEG-05 (~línea 417), `02` ~línea 592 y ADR-011 línea ~40 (ADR vigente, no se modifica; el alcance queda en ADR-062 punto 15). Opcional en `02` ~línea 591: "límite de intentos en la interfaz" puede precisarse como "10 fallos del PIN de desbloqueo".

---

## `02-arquitectura.md`

### §7.1 Nivel de aislamiento

**Texto actual**

> READ COMMITTED con bloqueos explícitos de fila. No se usa SERIALIZABLE por defecto.

**Texto propuesto**

> READ COMMITTED con bloqueos explícitos de fila. No se usa SERIALIZABLE por defecto. Excepción de solo lectura: el bootstrap (§13.4) se lee en una transacción `REPEATABLE READ READ ONLY` para que todas sus secciones sean del mismo instante (ADR-062).

### §11 API — códigos y rutas nuevas

**Texto propuesto (agregar):** `GET /api/v1/sync/bootstrap` (jornada `ABIERTA` propia en el dispositivo; 409 `JORNADA_REQUERIDA` sin ella; `since` aceptado e ignorado).

### §12.3 Sesión sin conexión

**Texto actual**

> - El PIN de desbloqueo se define con conexión y se guarda en el dispositivo como derivación PBKDF2 (Web Crypto) con sal e iteraciones altas.

**Texto propuesto**

> - El PIN de desbloqueo (6 dígitos, sin triviales) se define con conexión y se guarda en el dispositivo como derivación PBKDF2-SHA256 (Web Crypto) con sal de 32 bytes y 600 000 iteraciones; nunca viaja al servidor. Los fallos se cuentan en la base local; con 10 fallos (constante del código) se borra la derivación (ADR-062).

### §13.1 Áreas (última viñeta)

**Texto actual**

> Las páginas "Ver más" están en `/admin/ayuda/:tema`; `/ruta` montará las suyas cuando tenga pantallas (change 21).

**Texto propuesto**

> Las páginas "Ver más" están en `/admin/ayuda/:tema` y en `/ruta/ayuda/:tema`; dentro de `/ruta` y de la aplicación instalada el "Ver más" navega dentro de la aplicación (no abre otra pestaña), de modo que funciona sin conexión (ADR-062 punto 21).

### §13.2 Base local (Dexie)

**Texto actual:** la tabla de tablas (`meta`, `sesion`, `configuracion`, `productos`, `presentaciones`, `clientes`, `saldos_clientes`, `precios`, `reglas_descuento`, `stock`, `autorizadores`, `ventas`, `cobranzas`, `movimientos_locales`, `cola`).

**Texto propuesto (precisar la tabla y agregar al final)**

> En la versión 2 de Dexie (change 21) el saldo viaja dentro de `clientes` (no hay `saldos_clientes`) y las tablas maestras son las que reemplaza el bootstrap; `meta` guarda también el usuario local, la jornada, la fecha del bootstrap y la derivación del PIN con su contador de fallos (`pin_hash`, `pin_sal`, `pin_iteraciones`, `pin_intentos`). El bootstrap reemplaza las tablas maestras en una sola transacción sobre una lista explícita; `ventas`, `cobranzas`, `movimientos_locales` y `cola` las agrega la versión 3 (change 22a) y el bootstrap no las toca (ADR-062).

### §13.3 Motor de sincronización (última viñeta)

**Texto actual**

> - Al iniciar, solicita almacenamiento persistente (`navigator.storage.persist()`) y muestra una advertencia si el navegador lo niega.

**Texto propuesto**

> - Pide almacenamiento persistente (`navigator.storage.persist()`) tras el primer bootstrap y en cada arranque hasta que se conceda, y muestra una advertencia si el navegador lo niega (ADR-062 punto 18).

### §13.4 Bootstrap

**Texto actual**

> - `GET /api/v1/sync/bootstrap` se ejecuta al abrir la jornada (RUT-03) y devuelve el contenido de SYN-11.

**Texto propuesto**

> - `GET /api/v1/sync/bootstrap` se ejecuta al abrir la jornada, al iniciar sesión o desbloquear con conexión si faltan los datos de la jornada abierta, y con "Actualizar datos" (RUT-03); devuelve el contenido de SYN-11 en una sola foto (§7.1). Lo compone el módulo `sync` por el `service.py` de cada módulo (ADR-062).

### §13.5 Service worker

**Texto propuesto (agregar):** Se implementa con `vite-plugin-pwa` (`generateSW`, `registerType: 'prompt'`); precachea el shell, `/ruta`, la ayuda y pdfmake, no el código de `/admin`; el manifiesto abre en `/ruta`. Pide almacenamiento persistente tras el primer bootstrap y en cada arranque hasta que se conceda (ADR-062).

---

## `04-roadmap-changes.md`

### §11 — fila del 21

**Texto actual (celda "Entrega")**

> Service worker con shell, base Dexie, endpoint y consumo de bootstrap, sesión local con PIN, almacenamiento persistente, pantallas de ruta leyendo de Dexie

**Texto propuesto:** dejar la fila y agregar debajo de la tabla del hito 6 un párrafo con el estilo de los anteriores:

> **Change 21 (`pwa-y-bootstrap`) archivado (fecha de archivo) — terminado (ADR-062).** Entrega: `GET /api/v1/sync/bootstrap` en una sola foto de la base (jornada `ABIERTA` propia en el dispositivo; 409 `JORNADA_REQUERIDA`), Dexie v2 con reemplazo atómico de las tablas maestras, login propio de `/ruta`, PIN de desbloqueo de 6 dígitos (PBKDF2-SHA256, 600 000 iteraciones, pedido al abrir la aplicación; 10 fallos lo bloquean y piden el login), una sola sesión local por dispositivo, service worker con `vite-plugin-pwa` (precache del shell, `/ruta`, la ayuda y pdfmake; aviso de versión nueva sin recarga automática), almacenamiento persistente, las pantallas de consulta de `/ruta` (Inicio, Abrir jornada, Clientes y ficha, Productos, Stock, Mi cuenta, Ayuda) y el perfil `lan` de Docker Compose con Caddy de desarrollo (`tls internal`) para probar en un teléfono real. **Deudas saldadas:** del 13 (listas y versiones con `unidades_referencia`, sin costos), del 15 (bootstrap al abrir la jornada y apertura desde `/ruta`), del 16 (reglas con alcances, topes, `categoria_id` y `marca_id`), del 16b (`/ruta/ayuda/:tema` y "Ver más" interno), del 17 (permisos y medios activos), del 18a (último correlativo y versiones elegibles), del 18b (contexto de venta, autorizadores con derivación, crédito por cliente con tolerancia), del 20 (parámetros de la nota, nombre y CUIT de la organización, precache de pdfmake), del 20b (cartera "vacía = todos" y "Mi contraseña" en `/ruta`) y del 20c (motivos y alícuotas activos). **Deudas nuevas:** al **22a**, la guarda del carrito abierto frente a la versión nueva del service worker (`02` §13.5), las tablas de operaciones en Dexie (versión 3) y ampliar la prueba de que el bootstrap no las toca; al **22a**, también, la verificación local del PIN de supervisor con su límite de intentos en la interfaz (ya nominada por el 18b). **Pendiente de la prueba manual del usuario:** `04` §2.1 punto 5 (teléfono real) y la verificación futura en iPhone (D18).
