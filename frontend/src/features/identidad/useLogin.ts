import { useMutation } from '@tanstack/react-query'

import type { DatosLogin } from '../../domain/identidad/loginSchema'
import { iniciarSesionConContrasena, type RespuestaLogin } from './login'

export { ErrorDeLogin } from './login'

/** `02` §13.1: `/admin` corre en PC, así que un nombre fijo alcanza para esa pantalla. */
const NOMBRE_DISPOSITIVO_ADMIN = 'Administración (navegador)'

export function useLogin() {
  return useMutation({
    mutationFn: (datos: DatosLogin): Promise<RespuestaLogin> =>
      iniciarSesionConContrasena(datos, NOMBRE_DISPOSITIVO_ADMIN),
  })
}
