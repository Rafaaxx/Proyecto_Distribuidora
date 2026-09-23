import { z } from 'zod'

/** Validación del formulario de categorías y marcas (tarea 10.6): un único
 * campo obligatorio, igual regla en ambas entidades (`spec`
 * `categorias-y-marcas`, TR-10: nombre vacío o solo espacios se rechaza). */
export const esquemaNombreCategoriaOMarca = z.object({
  nombre: z.string().trim().min(1, 'Ingresá un nombre.'),
})

export type DatosNombreCategoriaOMarca = z.infer<typeof esquemaNombreCategoriaOMarca>
