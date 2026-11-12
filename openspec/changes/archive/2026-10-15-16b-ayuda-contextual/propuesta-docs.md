# Propuesta de cambios a `docs/` — change 16b `ayuda-contextual`

> **Pendiente de revisión del usuario. No se aplica a `docs/` sin su visto bueno.** Cada sección tiene el **texto actual** (copiado de `docs/` tal como está hoy) y el **texto propuesto** (lo que dejan las decisiones D0 a D10 de `design.md` con la opción A, a registrar en `docs/adr/ADR-051-ayuda-contextual.md`, estado *Propuesto*). Si el usuario elige otra opción en alguna decisión, esta propuesta se ajusta en la tarea 7.3.
>
> Orden: `00` §6.4; `02` §4, §13.1; `04` §2.1, §4, §8, §9.

---

## `00-vision-y-alcance.md`

### §6.4 Etapa 4 — Producto comercial (D1)

**Texto actual**

> - Documentación de usuario y ayuda contextual.

**Texto propuesto**

> - Documentación de usuario completa (manual, guías de tareas, búsqueda). La **ayuda contextual** —el botón "(?)" junto a los campos con reglas no obvias y las páginas "Ver más" de temas puntuales— se adelantó a la etapa 1 con el change 16b, y cada change que trae funcionalidad no obvia suma la suya (ADR-051).

---

## `02-arquitectura.md`

### §4 Estructura del repositorio — rama `frontend/src/` (D3, D7)

**Texto actual**

> ```
> │   ├── src/
> │   │   ├── app/               # ruteo, layouts, providers
> │   │   ├── areas/
> │   │   │   ├── ruta/
> │   │   │   └── admin/
> │   │   ├── features/          # por módulo de negocio
> │   │   ├── domain/            # motor de cálculo TS (§10.4)
> │   │   ├── sync/              # base local, cola, bootstrap, motor de sincronización
> │   │   ├── lib/               # dinero, cliente API, fechas, ids
> │   │   └── components/ui/
> ```

**Texto propuesto**

> ```
> │   ├── src/
> │   │   ├── app/               # ruteo, layouts, providers
> │   │   ├── areas/
> │   │   │   ├── ruta/
> │   │   │   └── admin/
> │   │   ├── features/          # por módulo de negocio
> │   │   ├── domain/            # motor de cálculo TS (§10.4)
> │   │   ├── sync/              # base local, cola, bootstrap, motor de sincronización
> │   │   ├── lib/               # dinero, cliente API, fechas, ids
> │   │   ├── ayuda/             # archivo único de textos de ayuda y páginas "Ver más" (ADR-051)
> │   │   └── components/ui/     # incluye Ayuda, el botón "(?)"
> ```

### §13.1 Áreas — viñeta nueva al final (D2, D5, D6, D7)

**Texto actual**

> - Las áreas se cargan de forma diferida: el teléfono no descarga el código de administración.
> - React Context se usa solo para sesión, permisos, conectividad y tema.
> - Las pantallas del área de ruta leen siempre de Dexie, con o sin conexión.

**Texto propuesto** (se agrega una viñeta)

> - Las áreas se cargan de forma diferida: el teléfono no descarga el código de administración.
> - React Context se usa solo para sesión, permisos, conectividad y tema.
> - Las pantallas del área de ruta leen siempre de Dexie, con o sin conexión.
> - **Ayuda contextual (ADR-051):** el componente `Ayuda` ("(?)") abre un panel no modal con clic, tap o teclado y cierra con Escape o clic afuera. Todos sus textos viven en `frontend/src/ayuda/textos.ts`, por clave, con los IDs de regla que citan; no piden nada a la red ni dependen de permisos, así que también sirven sin conexión. Las páginas "Ver más" están en `/admin/ayuda/:tema`; `/ruta` montará las suyas cuando tenga pantallas (change 21). Una prueba de Vitest verifica que toda clave usada exista y que todo ID citado exista en `01-dominio.md` o en `docs/adr/`.

---

## `04-roadmap-changes.md`

### §2.1 Definición de terminado — punto 8 nuevo (D10)

**Texto actual**

> Un change está terminado cuando:
>
> 1. Las pruebas que exige `02` §15 para su alcance pasan en CI.
> 2. Cada escenario de sus specs tiene al menos una prueba que lo cubre.
> 3. Los invariantes que toca tienen prueba que los cita por ID.
> 4. La migración de Alembic sube y baja limpia sobre una base con datos.
> 5. Se probó a mano el flujo principal en el navegador.
> 6. Las specs delta se archivaron en `openspec/specs/` y `04-roadmap-changes.md` quedó actualizado.
> 7. Si se tomó una decisión nueva, quedó como ADR.

**Texto propuesto**

> Un change está terminado cuando:
>
> 1. Las pruebas que exige `02` §15 para su alcance pasan en CI.
> 2. Cada escenario de sus specs tiene al menos una prueba que lo cubre.
> 3. Los invariantes que toca tienen prueba que los cita por ID.
> 4. La migración de Alembic sube y baja limpia sobre una base con datos.
> 5. Se probó a mano el flujo principal en el navegador.
> 6. Las specs delta se archivaron en `openspec/specs/` y `04-roadmap-changes.md` quedó actualizado.
> 7. Si se tomó una decisión nueva, quedó como ADR.
> 8. Si el change trae funcionalidad no obvia, sus pantallas traen su ayuda contextual ("(?)" y, si el tema es largo, su página "Ver más") en el archivo único de textos, cada texto citando la regla de `01-dominio.md` o el ADR en que se apoya. Si el change modifica una regla o un ADR, se revisan los textos que lo citan (se buscan por su ID). Las tareas del change dicen qué claves agrega o revisa, o "no aplica" (ADR-051).

### §4 Tabla de dependencias — fila nueva entre 16 y 17 (D0, D1)

**Texto actual**

> | 16 motor-de-descuentos | 05, 13 |
> | 17 cobranzas | 07, 08, 15 |

**Texto propuesto**

> | 16 motor-de-descuentos | 05, 13 |
> | 16b ayuda-contextual | 13, 14, 15, 16 |
> | 17 cobranzas | 07, 08, 15 |

(El 16b depende de los changes cuyas pantallas reciben ayuda: precios 13, compras y costos 11 y 11b —ya cubiertos por el 13—, stock 14 y 15, descuentos 16. Ningún change depende del 16b: el 17 y los siguientes solo suman claves al archivo, por el punto 8 de §2.1.)

### §8 Hito 4 — fila nueva entre 16 y 17

**Texto actual**

> | 16 | `motor-de-descuentos` | Reglas de volumen, alcance, prioridad, acumulabilidad y vigencia; motor en Python y TypeScript; descuento manual (general por venta y propio por línea) con tope y autorización; tope de descuento por rol; fixtures compartidos DSC-05 y DSC-06; pantallas de reglas y de topes. El efecto en la venta es del 18b | — |
> | 17 | `cobranzas` | Cobranza independiente con varios medios, anulación, efecto en cuenta corriente | INV-08, CC-05 |

**Texto propuesto**

> | 16 | `motor-de-descuentos` | (sin cambio) | — |
> | 16b | `ayuda-contextual` | Botón "(?)" accesible (clic, tap, teclado), archivo único de textos con IDs de regla y prueba de trazabilidad, páginas "Ver más" (descuentos, topes, precio de una lista) y ayuda en las pantallas de descuentos, topes, listas de precios, compras, costos, ubicaciones y jornadas. Adelanta la ayuda contextual de la etapa 4 (ADR-051) | — |
> | 17 | `cobranzas` | (sin cambio) | INV-08, CC-05 |

### §8 — párrafo nuevo después de los del change 16 (al archivar)

**Texto propuesto**

> **Change 16b (`ayuda-contextual`) — deudas nuevas (ADR-051):** **al change 18b:** los "(?)" del descuento manual en la venta (porcentaje general y propio por línea, tope y autorización), reutilizando las claves y el tema `topes`. **Al change 21:** la ruta de ayuda en `/ruta` (`/ruta/ayuda/:tema`) con la misma página de tema, sin conexión; en la PWA instalada, "Ver más" navega a la ruta interna en lugar de abrir otra pestaña. **Duda abierta de `01`:** PRC-11 no dice de qué presentación sale el costo cuando hay "costos distintos por presentación"; la ayuda de esa señal no lo explica hasta que se precise.

### §2 Convenciones — tamaño

Sin cambio: el 16b entra en el tamaño de `04` §2 (D0 = A). Si el usuario elige D0 = B, se agrega además la fila `16c ayuda-compras-y-stock | 16b` en §4 y §8.
