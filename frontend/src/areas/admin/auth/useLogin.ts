import { useMutation } from '@tanstack/react-query'

import type { DatosLogin } from '../../../domain/identidad/loginSchema'
import { apiFetch } from '../../../lib/api/httpClient'
import { fijarAccessToken } from '../../../lib/auth/tokenStore'
import { obtenerOGenerarDispositivoId } from '../../../lib/dispositivo/dispositivoId'

/**
 * `docs/02-arquitectura.md` §13.1: `/admin` usa TanStack Query contra la
 * API. El nombre del dispositivo es un dato descriptivo, no una regla de
 * negocio: `02` §13.1 fija que `/admin` corre en PC, así que un nombre fijo
 * alcanza para esta pantalla (sin inventar una UX de "nombrá tu
 * dispositivo" que ningún escenario de la spec pide).
 */
const NOMBRE_DISPOSITIVO_ADMIN = 'Administración (navegador)'

interface RespuestaLogin {
  access_token: string
}

interface ProblemDetails {
  title?: string
}

/** Mensaje de reserva si la respuesta de error no trae `title` (nunca
 * debería pasar contra este backend, pero un componente no debe reventar
 * si pasa). No reemplaza el mensaje indistinguible del servidor: solo
 * cubre una respuesta malformada. */
const MENSAJE_GENERICO_DE_RESERVA = 'No se pudo iniciar sesión.'

export class ErrorDeLogin extends Error {}

export function useLogin() {
  return useMutation({
    mutationFn: async (datos: DatosLogin): Promise<RespuestaLogin> => {
      const dispositivoId = await obtenerOGenerarDispositivoId()

      const respuesta = await apiFetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          organizacion_slug: datos.organizacionSlug,
          usuario: datos.usuario,
          contrasena: datos.contrasena,
          dispositivo_id: dispositivoId,
          nombre_dispositivo: NOMBRE_DISPOSITIVO_ADMIN,
        }),
      })

      if (!respuesta.ok) {
        const problema = (await respuesta.json()) as ProblemDetails
        // El mensaje viene tal cual del backend: la indistinguibilidad
        // entre "contraseña incorrecta" y "usuario inexistente" (spec
        // `identidad/autenticacion-y-sesion`) es una garantía del servidor
        // (mismo código, mismo mensaje); acá no se agrega ninguna
        // distinción propia.
        throw new ErrorDeLogin(problema.title ?? MENSAJE_GENERICO_DE_RESERVA)
      }

      const datosToken = (await respuesta.json()) as RespuestaLogin
      fijarAccessToken(datosToken.access_token)
      return datosToken
    },
  })
}
