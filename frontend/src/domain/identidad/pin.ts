/**
 * PIN de autorización y "Mi PIN" (change 18b, tareas 14.2 y 14.3; `design.md` D21; SEG-05,
 * ADR-011, ADR-019). Lógica pura de las pantallas: quién aparece en la lista, la validación local
 * del PIN nuevo (ayuda: el servidor valida igual y es quien decide si es "trivial", TR-10) y los
 * mensajes de error. Ninguna función guarda el PIN: lo reciben y lo devuelven.
 */

import type { CodigoPermiso } from './permisos'
import { PERMISOS_DE_AUTORIZACION } from './roles'

/** Los permisos de autorización de excepciones (ADR-011), tipados; una prueba exige que sean los de `roles.ts`. */
export const PERMISOS_DE_MI_PIN = [
  'AUTORIZAR_DESCUENTO',
  'SUPERAR_CREDITO',
  'VENDER_CLIENTE_SUSPENDIDO',
  'USAR_LISTA_ANTERIOR',
] as const satisfies readonly CodigoPermiso[]

/** La entrada "Mi PIN" se ofrece solo a quien tiene algún permiso de autorización (D21 punto 9). */
export function ofreceMiPin(tiene: (permiso: CodigoPermiso) => boolean): boolean {
  return PERMISOS_DE_MI_PIN.some((permiso) => tiene(permiso))
}

export type ResultadoDePinNuevo = { valido: true } | { valido: false; mensaje: string }

/** Al menos 6 dígitos ASCII, sin letras ni espacios (ADR-019). */
const PIN_CON_FORMATO = /^[0-9]{6,}$/

/** Ayuda local antes de enviar: formato y que las dos veces coincidan. */
export function validarPinNuevo(pin: string, repeticion: string): ResultadoDePinNuevo {
  if (!PIN_CON_FORMATO.test(pin)) {
    return { valido: false, mensaje: 'El PIN tiene que tener al menos 6 números, sin letras ni espacios.' }
  }
  if (pin !== repeticion) return { valido: false, mensaje: 'Los dos PIN tienen que ser iguales.' }
  return { valido: true }
}

const MENSAJES_POR_CODIGO: Record<string, string> = {
  IDENTIDAD_CONTRASENA_INCORRECTA: 'La contraseña no es correcta.',
  IDENTIDAD_PIN_AUTORIZACION_INVALIDO:
    'El PIN no sirve: tiene que tener al menos 6 números y no puede ser fácil de adivinar, como 123456 o 111111.',
  PERMISO_REQUERIDO: 'No tenés permiso para hacer esto.',
  IDENTIDAD_ROL_SIN_AUTORIZACION_PARA_PIN:
    'El rol de esa persona no autoriza excepciones, así que no puede tener PIN de autorización.',
}

/**
 * Mensaje para mostrar. El bloqueo por intentos (`IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS`) conserva
 * el del servidor, que trae el momento del desbloqueo.
 */
export function mensajeDeErrorDePin(codigo: string | null, mensajeDelServidor: string): string {
  return (codigo !== null ? MENSAJES_POR_CODIGO[codigo] : undefined) ?? mensajeDelServidor
}

export interface UsuarioParaPin {
  id: string
  nombre: string
  rol_id: string
  estado: string
  tiene_pin_autorizacion: boolean
}

export interface RolParaPin {
  id: string
  nombre: string
  activo: boolean
  permisos: readonly string[]
}

export interface FilaDelPin {
  usuarioId: string
  nombre: string
  rol: string
  tienePin: boolean
}

/**
 * Los usuarios activos cuyo rol (activo) confiere algún permiso de autorización, por nombre, con
 * "PIN definido" (nunca la derivación, D21 parte A).
 */
export function filasDelPinDeAutorizacion(
  usuarios: readonly UsuarioParaPin[],
  roles: readonly RolParaPin[],
): FilaDelPin[] {
  const porId = new Map(roles.map((rol) => [rol.id, rol]))
  return usuarios
    .flatMap((usuario) => {
      const rol = porId.get(usuario.rol_id)
      if (usuario.estado !== 'ACTIVO' || rol === undefined || !rol.activo) return []
      if (!rol.permisos.some((permiso) => PERMISOS_DE_AUTORIZACION.includes(permiso))) return []
      return [{ usuarioId: usuario.id, nombre: usuario.nombre, rol: rol.nombre, tienePin: usuario.tiene_pin_autorizacion }]
    })
    .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'))
}
