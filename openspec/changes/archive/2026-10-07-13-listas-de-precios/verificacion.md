# Verificación manual — change 13 `listas-de-precios` (tarea 17.2)

> **Pendiente: la ejecuta el usuario en el navegador.** Esta lista la dejó preparada el apply del Lote 4; los resultados están vacíos y la tarea 17.2 **no está marcada** hasta que el usuario registre acá lo que vio.

## Preparación

- [x] Levantar el entorno: `docker compose up -d` (sin reconstruir imágenes: ningún lote agregó dependencias, tarea 17.1) y aplicar `alembic upgrade head` (revisión `e2f3a4b5c6d7`).
- [x] Usuarios de prueba (rol → permisos relevantes): **Administrador** (`GESTIONAR_LISTAS`, `PUBLICAR_LISTAS`, `ADMIN_CONFIGURACION`, `VER_COSTOS`); **Administración** (`GESTIONAR_LISTAS`, `VER_COSTOS`, sin `PUBLICAR_LISTAS`); un usuario con `GESTIONAR_LISTAS` y `PUBLICAR_LISTAS` **sin** `VER_COSTOS`; un **Vendedor** (sin permisos de listas).
- [x] Datos: unos productos con presentación de referencia y costos informados (p. ej. Vino A, caja x6, costo base $1.000 por botella), una categoría "Vinos", un proveedor.

## Pasos y resultado

| # | Paso (con el Administrador, salvo que se indique) | Qué debería verse | Resultado |
| --- | --- | --- | --- |
| 1 | `/admin` → "Listas de precios" → "Nueva lista": nombre `General`, múltiplo `100`, dirección "Hacia arriba" | La lista se crea y se abre su detalle | |
| 2 | Configuración → "Lista predeterminada": sin lista definida | Advertencia "los clientes sin lista asignada no tienen precio". Elegir `General` y guardar: se muestra como lista predeterminada actual y desaparece la advertencia | |
| 3 | En el detalle de `General`: crear una regla "Toda la lista", margen bruto 30%; una de categoría "Vinos", markup 30%; una de producto (Vino A) | Cada regla muestra su fórmula (`Precio = costo ÷ 0,70`, `Precio = costo × 1,30`). Una regla de margen bruto de 100% se marca inválida; repetir la regla de la categoría muestra `REGLA_DUPLICADA` junto al alcance y conserva lo cargado | |
| 4 | Definir un redondeo por categoría (Vinos, múltiplo 50, "Al más cercano") | Aparece en "Redondeo por categoría" | |
| 5 | "Borrador" → "Generar borrador" | Tabla de precios (precio anterior —, nuevo, "Nuevo", costo, regla y calculado con `VER_COSTOS`), productos sin precio con su causa (sin costo, sin regla, sin presentación de referencia), fecha de generación y el aviso "Publicar no recalcula". Debajo de cada producto, el precio por presentación de venta (p. ej. botella y caja x6), que ahora sale de las presentaciones que trae la propia línea del borrador (ajuste B: la pantalla ya no pide el detalle de cada producto; en las herramientas de red del navegador no deben aparecer pedidos `/catalogo/productos/<id>`) | |
| 6 | Revisar los productos sin precio; fijar un precio manual a uno (p. ej. $9.000) y comprobar un importe inválido (`0`) | El manual queda marcado "Manual"; el importe `0` se rechaza junto al campo | |
| 7 | Quitar el precio manual de un producto | El precio vuelve a calcularse | |
| 8 | Publicar (con el Administrador) sin vigencias; confirmar "N precios, M productos sin precio" | La versión aparece "Vigente" en el detalle | |
| 9 | Informar un costo nuevo para Vino A (p. ej. $1.100 por botella), volver al borrador y "Regenerar" | Se ve el precio anterior → nuevo ("Cambia"), la botella con PRC-22 (p. ej. $1.583,33 sobre caja x6 a $9.500) siguen viéndose igual que antes del ajuste B y la señal "Margen menor que el de la regla" en el producto con precio manual (criterio 3 de `00` §9) | |
| 10 | Publicar una versión **programada** (vigencia desde futura) y luego anularla desde su pantalla | "Anular" solo aparece en la versión programada; queda "Anulada" con quién y cuándo | |
| 11 | Intentar anular la versión **vigente** | No hay botón "Anular"; la versión es de solo lectura | |
| 12 | Publicar con una vigencia desde en el pasado | `VIGENCIA_INVALIDA` junto a la fecha; el borrador sigue sin publicar | |
| 13 | Abrir una versión anterior (histórica) | Se ve de solo lectura, sin controles de edición, y cada producto muestra su precio por presentación (p. ej. Vino A: botella $1.583,33 y caja x6 $9.500,00) | |
| 14 | En la ficha de un cliente (con un usuario con solo `GESTIONAR_CLIENTES`, si hay): elegir la lista `General` o "Predeterminada de la organización" y guardar | El selector ofrece solo las listas activas; la lista queda asignada. Después, editar el cliente, corregir otro dato y guardar sin tocar el selector: la lista asignada se conserva (ajuste A); elegir "Predeterminada de la organización" la quita | |
| 15 | Intentar desactivar `General` (lista predeterminada o asignada a un cliente) desde "Editar lista" | `LISTA_EN_USO` con la explicación; la lista sigue activa | |
| 16 | Usuario con solo `GESTIONAR_LISTAS` (sin "Publicar") | Ve "Regenerar" y la edición de precios; no ve "Publicar" | |
| 17 | Usuario sin `VER_COSTOS` | Ve precios y señales; no ve costo de referencia, regla ni precio calculado | |
| 18 | Vendedor (sin permisos de listas) | No ve "Listas de precios" en el menú; la ruta directa dice que no tiene permiso y no pide datos | |

## Observaciones del usuario

- 2026-10-07: el usuario probó el flujo completo en el navegador, con el backend reconstruido tras los ajustes del grupo 18, y lo dio por bueno.
- La entrada "Lista predeterminada" de Configuración es poco visible (enlace chico junto a "Fiscal"); el usuario la encontró tras indicársela. No bloquea.
- Para el paso 5.2 (usuario con listas y sin `VER_COSTOS`) se indicó usar el rol Consulta/Dirección con `GESTIONAR_LISTAS` y `PUBLICAR_LISTAS` agregados por API, porque ningún rol de fábrica combina esos permisos y la interfaz no crea roles.

## Cierre

- [x] El usuario aprobó la verificación y la tarea 17.2 puede marcarse.
