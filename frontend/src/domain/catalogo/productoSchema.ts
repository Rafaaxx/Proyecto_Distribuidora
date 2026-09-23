import { z } from 'zod'

/**
 * Validación del formulario de alta/edición de producto y presentaciones
 * (tarea 10.3). Espejo en el cliente de las reglas que el servidor exige
 * de todos modos (`catalogo/domain/presentaciones.py::validar_alta_presentaciones`,
 * spec `productos-y-presentaciones`): esto es UX -- evita un viaje al
 * servidor para un error obvio -- nunca la fuente de verdad, que sigue
 * siendo el 422/409 del backend (mostrado junto al campo, tarea 10.5).
 */

const MENSAJE_REQUERIDO = 'Este campo es obligatorio.'

export const esquemaPresentacion = z.object({
  nombre: z.string().trim().min(1, MENSAJE_REQUERIDO),
  unidadesBase: z
    .number({ error: 'Las unidades deben ser un número entero mayor o igual a 1.' })
    .int('Las unidades deben ser un número entero mayor o igual a 1.')
    .min(1, 'Las unidades deben ser un número entero mayor o igual a 1.'),
  usarEnVenta: z.boolean(),
  usarEnCompra: z.boolean(),
  esReferencia: z.boolean(),
})

export type DatosPresentacion = z.infer<typeof esquemaPresentacion>

/** Edición de una presentación ya existente (tarea 10.5): agrega `activo`
 * (CAT-05, desactivar/reactivar) a los mismos campos del alta. */
export const esquemaPresentacionModificar = esquemaPresentacion.extend({ activo: z.boolean() })

export type DatosPresentacionModificar = z.infer<typeof esquemaPresentacionModificar>

/** CAT-03: exactamente una presentación de referencia. */
function tieneExactamenteUnaReferencia(presentaciones: DatosPresentacion[]): boolean {
  return presentaciones.filter((presentacion) => presentacion.esReferencia).length === 1
}

/** CAT-03: la referencia tiene que poder venderse (`usarEnVenta`) -- una
 * referencia que no se usa en venta no sirve para expresar cantidades
 * vendidas en esa unidad. Solo se evalúa cuando ya hay una única
 * referencia (si no la hay, el mensaje de arriba ya lo cubre). */
function laReferenciaSeUsaEnVenta(presentaciones: DatosPresentacion[]): boolean {
  const referencias = presentaciones.filter((presentacion) => presentacion.esReferencia)
  if (referencias.length !== 1) {
    return true
  }
  return referencias[0]?.usarEnVenta ?? true
}

/** Campos base del producto, comunes al alta y a la edición (tarea 10.5:
 * la edición no vuelve a mandar las presentaciones -- esas se gestionan
 * aparte, por sus propios comandos `PRESENTACION_AGREGAR`/`_MODIFICAR`). */
export const camposProductoBase = {
  codigo: z.string().trim().min(1, MENSAJE_REQUERIDO),
  nombre: z.string().trim().min(1, MENSAJE_REQUERIDO),
  categoriaId: z.uuid('Elegí una categoría.'),
  marcaId: z.uuid('Marca inválida.').nullable(),
  unidadBase: z.string().trim().min(1, MENSAJE_REQUERIDO),
  alicuotaId: z.uuid('Elegí una alícuota.'),
}

export const esquemaProductoBase = z.object({
  ...camposProductoBase,
  activo: z.boolean(),
})

export type DatosProductoBase = z.infer<typeof esquemaProductoBase>

export const esquemaProducto = z
  .object({
    ...camposProductoBase,
    // CAT-02: "una o más presentaciones".
    presentaciones: z.array(esquemaPresentacion).min(1, 'Agregá al menos una presentación (CAT-02).'),
  })
  .refine((datos) => tieneExactamenteUnaReferencia(datos.presentaciones), {
    message: 'Debe haber exactamente una presentación de referencia (CAT-03).',
    path: ['presentaciones'],
  })
  .refine((datos) => laReferenciaSeUsaEnVenta(datos.presentaciones), {
    message: 'La presentación de referencia debe usarse en venta (CAT-03).',
    path: ['presentaciones'],
  })

export type DatosProducto = z.infer<typeof esquemaProducto>
