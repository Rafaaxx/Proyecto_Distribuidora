import { z } from 'zod'

/**
 * Validación pura del formulario de inicio de sesión (tarea 13.4). Los
 * componentes no contienen lógica de negocio (`CLAUDE.md` §5): esta
 * validación vive en `domain/`, no en `LoginScreen.tsx`.
 */
export const esquemaLogin = z.object({
  organizacionSlug: z.string().min(1, 'Ingresá el identificador de la organización.'),
  usuario: z.string().min(1, 'Ingresá el usuario.'),
  contrasena: z.string().min(1, 'Ingresá la contraseña.'),
})

export type DatosLogin = z.infer<typeof esquemaLogin>
