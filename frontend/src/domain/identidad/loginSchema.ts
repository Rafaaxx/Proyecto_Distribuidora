import { z } from 'zod'

/**
 * Validación pura del formulario de inicio de sesión (tarea 13.4). Los
 * componentes no contienen lógica de negocio (`CLAUDE.md` §5): esta
 * validación vive en `domain/`, no en `LoginScreen.tsx`.
 *
 * Organización y usuario se recortan (`trim`) antes de enviarse: el teclado del teléfono suele
 * agregar un espacio al final y el servidor compara tal cual (ADR-057, enmienda 2026-11-08). La
 * contraseña NO se recorta: los espacios pueden ser parte de ella.
 */
export const esquemaLogin = z.object({
  organizacionSlug: z.string().trim().min(1, 'Ingresá el identificador de la organización.'),
  usuario: z.string().trim().min(1, 'Ingresá el usuario.'),
  contrasena: z.string().min(1, 'Ingresá la contraseña.'),
})

export type DatosLogin = z.infer<typeof esquemaLogin>
