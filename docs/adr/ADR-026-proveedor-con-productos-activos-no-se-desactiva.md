# ADR-026 — Un proveedor con productos activos no se puede desactivar (CAT-01, CAT-05, CAT-06)

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-23 |
| Referenciado en | `openspec/changes/06-proveedores-y-costos-informados/design.md` D5 (y D9, D14); `01-dominio.md` CAT-01, CAT-05, CAT-06; ADR-024 |

**Regla (D5, opción A) aprobada por el usuario el 2026-09-23. Texto del ADR aprobado por el usuario el 2026-09-23; estado *Vigente*.**

## Contexto

A partir del change 06 todo producto tiene exactamente un proveedor obligatorio (CAT-01, CAT-06 en etapa 1). `01-dominio.md` no dice qué hace un proveedor inactivo ni si puede desactivarse mientras tiene productos activos asignados: es el mismo vacío que ADR-024 resolvió para la categoría, que también es obligatoria en el producto.

La regla afecta a más de un módulo (`catalogo` al asignar proveedor, `proveedores` al desactivarlo y al registrar costos) y a changes futuros (importación del 10, compras del 11, varios proveedores en la etapa 4), por eso se registra como ADR en vez de dejarla solo en `design.md`, con el mismo criterio que ADR-024.

## Decisión

1. `PROVEEDOR_MODIFICAR` con `activo=false` se rechaza con `PROVEEDOR_CON_PRODUCTOS_ACTIVOS` si existe al menos un producto activo de la misma `organizacion_id` con `proveedor_id` igual al proveedor que se intenta desactivar. `proveedores` lo consulta a través de `catalogo/service.py` (dirección de dependencia permitida por `02` §5.3). Sin productos activos asignados, la desactivación se acepta.
2. Un proveedor inactivo **no se asigna** a un producto: `PRODUCTO_CREAR`, o `PRODUCTO_MODIFICAR` con un proveedor distinto del actual, se rechaza con `PROVEEDOR_INACTIVO` (validado por el puerto de ADR-025). **Conservar** el proveedor actual inactivo en `PRODUCTO_MODIFICAR` se acepta.
3. Un proveedor inactivo **no recibe costos informados**: `COSTO_INFORMAR` se rechaza con `PROVEEDOR_INACTIVO`.

## Consecuencias

- Por efecto de `PROVEEDOR_MODIFICAR`, ningún producto activo queda con un proveedor inactivo, simétrico con ADR-024 para la categoría.
- Sí pueden existir productos con proveedor inactivo por otras vías, y la regla 2 los admite: productos inactivos cuyo proveedor se desactivó después, y los productos que la migración del change 06 asigna al proveedor provisorio inactivo "Proveedor a asignar" (`design.md` D2). Por eso conservar la asignación actual se acepta.
- Para dejar de trabajar con un proveedor, primero se reasignan o desactivan sus productos activos; no hay reasignación masiva en el change 06 (fricción de operación conocida).
- La carrera entre desactivar un proveedor y asignarlo a un producto se cierra con `FOR UPDATE` en `PROVEEDOR_MODIFICAR` y `FOR SHARE` en la consulta de ADR-025 y en `COSTO_INFORMAR` (D14).
- El historial de costos informados de un proveedor desactivado no cambia (CST-03).
- Sin cambio de esquema: la validación es de servicio.
- Cuando la etapa 4 admita varios proveedores por producto, esta regla se revisa con un ADR nuevo.

## Alternativas consideradas

- **Permitir desactivar libremente.** Descartada: dejaría productos activos con un proveedor al que no se le pueden cargar costos hasta reasignarlo, y rompería la simetría con ADR-024 sin una regla de `01` que lo justifique.
- **Desactivar en cascada los productos del proveedor.** Descartada por el mismo motivo que en ADR-024: una escritura sobre `proveedor` no debe modificar filas de `producto` fuera del comando pedido; oculta el alcance real y complica la auditoría.
- **Rechazar también conservar un proveedor inactivo en `PRODUCTO_MODIFICAR`.** Descartada: impediría editar cualquier otro dato de un producto asignado al proveedor provisorio de la migración sin reasignarlo en el mismo paso.
