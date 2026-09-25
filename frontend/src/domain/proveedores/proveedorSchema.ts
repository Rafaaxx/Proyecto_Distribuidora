import { z } from 'zod'

/**
 * Validación del formulario de proveedor (tarea 11.3): nombre obligatorio
 * (TR-10: vacío o solo espacios se rechaza, mismo criterio que
 * `categoriaMarcaSchema.ts`); CUIT, contacto, teléfono y email opcionales
 * -- la validación de fondo (formato de CUIT, duplicados) la hace el
 * servidor (`CUIT_INVALIDO`, `CUIT_DUPLICADO`, `design.md` D7); esto es
 * solo UX.
 */
// `cuit`/`contacto`/`telefono`/`email` llegan de un `<input>` de texto: el
// componente convierte `''` a `null` con `setValueAs` (mismo criterio que
// `marcaId` en `productoSchema.ts`) antes de que Zod los vea, así que acá
// ya son `string | null`.
const camposProveedor = {
  nombre: z.string().trim().min(1, 'Ingresá un nombre.'),
  cuit: z.string().nullable(),
  contacto: z.string().nullable(),
  telefono: z.string().nullable(),
  email: z.string().nullable(),
}

export const esquemaProveedorCrear = z.object(camposProveedor)
export type DatosProveedorCrear = z.infer<typeof esquemaProveedorCrear>

export const esquemaProveedorModificar = z.object({
  ...camposProveedor,
  activo: z.boolean(),
})
export type DatosProveedorModificar = z.infer<typeof esquemaProveedorModificar>
