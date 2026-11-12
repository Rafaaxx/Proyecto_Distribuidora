import { z } from 'zod'

import { esquemaTope } from './topes'

/**
 * Reglas puras de las pantallas de usuarios, roles y "Mi contraseña" (change 20b, grupo 10; D5,
 * D6, D8, D9, D10, D12, D16, D20; ADR-027, ADR-028, ADR-053, ADR-056, DSC-06, INV-01, INV-03).
 * Todo esto es ayuda de la interfaz: el servidor valida igual y es quien decide. Ninguna función
 * guarda una contraseña: la reciben y la devuelven.
 */

/** Mismos límites que `identidad/domain/usuarios.py` (D9, D10, D20). */
const LARGO_MAXIMO_NOMBRE_DE_USUARIO = 200
const LARGO_MAXIMO_NOMBRE_DE_ROL = 100
const LARGO_MINIMO_DE_CONTRASENA = 8

const MENSAJE_CONTRASENA_CORTA = `La contraseña tiene que tener al menos ${LARGO_MINIMO_DE_CONTRASENA} caracteres.`
const MENSAJE_CONFIRMACION = 'Las dos contraseñas tienen que ser iguales.'

const nombreDePersona = z
  .string()
  .transform((valor) => valor.trim())
  .pipe(
    z
      .string()
      .min(1, 'Escribí el nombre.')
      .max(LARGO_MAXIMO_NOMBRE_DE_USUARIO, `El nombre tiene hasta ${LARGO_MAXIMO_NOMBRE_DE_USUARIO} caracteres.`),
  )

const emailOpcional = z.string().transform((valor) => {
  const recortado = valor.trim()
  return recortado === '' ? null : recortado
})

/** Contraseña nueva: no en blanco y con el largo mínimo, sin reglas de composición (D9). */
const contrasenaNueva = z
  .string()
  .refine((valor) => valor.trim() !== '', 'La contraseña no puede estar en blanco.')
  .refine((valor) => valor.length >= LARGO_MINIMO_DE_CONTRASENA, MENSAJE_CONTRASENA_CORTA)

export const esquemaAltaDeUsuario = z
  .object({
    usuario: z
      .string()
      .transform((valor) => valor.trim())
      .pipe(z.string().min(1, 'Escribí el nombre de usuario con el que va a entrar.')),
    nombre: nombreDePersona,
    email: emailOpcional,
    rol_id: z.string().min(1, 'Elegí un rol.'),
    password: contrasenaNueva,
    confirmacion: z.string(),
  })
  .refine((datos) => datos.password === datos.confirmacion, { path: ['confirmacion'], message: MENSAJE_CONFIRMACION })
  .transform(({ usuario, nombre, email, rol_id, password }) => ({ usuario, nombre, email, rol_id, password }))

export type DatosDeAltaDeUsuario = z.output<typeof esquemaAltaDeUsuario>

export const esquemaEdicionDeUsuario = z.object({ nombre: nombreDePersona, email: emailOpcional })

export type DatosDeEdicionDeUsuario = z.output<typeof esquemaEdicionDeUsuario>

/** Restablecimiento por el administrador (D8): la confirmación es solo de interfaz. */
export const esquemaContrasenaDeUsuario = z
  .object({ contrasena: contrasenaNueva, confirmacion: z.string() })
  .refine((datos) => datos.contrasena === datos.confirmacion, { path: ['confirmacion'], message: MENSAJE_CONFIRMACION })
  .transform(({ contrasena }) => ({ contrasena }))

/**
 * "Mi contraseña" (D20): la actual y la nueva viajan; la confirmación es solo de interfaz. Que la
 * nueva sea distinta de la actual lo decide el servidor (no cuenta como intento fallido).
 */
export const esquemaMiContrasena = z
  .object({
    actual: z.string().min(1, 'Escribí tu contraseña actual.'),
    nueva: contrasenaNueva,
    confirmacion: z.string(),
  })
  .refine((datos) => datos.nueva === datos.confirmacion, { path: ['confirmacion'], message: MENSAJE_CONFIRMACION })
  .transform(({ actual, nueva }) => ({ actual, nueva }))

export type DatosDeMiContrasena = z.output<typeof esquemaMiContrasena>

/**
 * Tope propio (D12): se escribe como porcentaje y viaja como fracción de seis decimales; vacío
 * es `null` (vuelve a regir el del rol). Mismas reglas que el tope de rol.
 */
export const esquemaTopePropio = z
  .object({ tope_descuento: z.string() })
  .transform((datos, contexto): { tope_descuento: string | null } => {
    if (datos.tope_descuento.trim() === '') return { tope_descuento: null }
    const resultado = esquemaTope.safeParse(datos)
    if (resultado.success) return resultado.data
    for (const problema of resultado.error.issues) {
      contexto.addIssue({ code: 'custom', path: problema.path, message: problema.message })
    }
    return z.NEVER
  })

/** El tope propio no tiene efecto si el rol no puede dar descuento manual (DSC-06, D12). */
export function topePropioSinEfecto(permisosDelRol: readonly string[], topePropio: string | null): boolean {
  return topePropio !== null && !permisosDelRol.includes('DESCUENTO_MANUAL')
}

export const esquemaNombreDeRol = z.object({
  nombre: z
    .string()
    .transform((valor) => valor.trim())
    .pipe(
      z
        .string()
        .min(1, 'Escribí el nombre del rol.')
        .max(LARGO_MAXIMO_NOMBRE_DE_ROL, `El nombre del rol tiene hasta ${LARGO_MAXIMO_NOMBRE_DE_ROL} caracteres.`),
    ),
})

/** "Nuevo rol": el nombre y, solo de interfaz, de qué rol copiar los permisos (vacío: ninguno). */
export const esquemaNuevoRol = z.object({
  nombre: esquemaNombreDeRol.shape.nombre,
  copiarDe: z.string(),
})

interface RolElegible {
  id: string
  activo: boolean
}

/** Los selectores de rol ofrecen solo los activos; el rol actual del usuario se conserva para mostrarlo (D7, D9). */
export function rolesAsignables<T extends RolElegible>(roles: readonly T[], rolActualId?: string): T[] {
  return roles.filter((rol) => rol.activo || rol.id === rolActualId)
}

/** "3 (1 inactivo)", "3 (2 inactivos)" o solo "3" (tarea 8.6, decidido el 2026-10-28). */
export function textoDeTopesPorRol(total: number, inactivos: number): string {
  if (inactivos <= 0) return String(total)
  return `${total} (${inactivos} ${inactivos === 1 ? 'inactivo' : 'inactivos'})`
}

/** El número de "Topes por rol" lleva al listado de usuarios de ese rol con tope propio. */
export function enlaceDeUsuariosConTopePropio(rolId: string): string {
  return `/admin/usuarios?rol_id=${encodeURIComponent(rolId)}&con_tope_propio=true`
}

export interface DatosParaAvisosDeBaja {
  /** Nombres de las ubicaciones de las jornadas no cerradas del usuario. */
  jornadas: readonly string[]
  clientesAsignados: number
  /** El conteo llegó al máximo leído: hay más. */
  masDeLosContados: boolean
}

/** Avisos de D6 antes de confirmar la baja: no la impiden, la realidad física manda. */
export function avisosDeBaja({ jornadas, clientesAsignados, masDeLosContados }: DatosParaAvisosDeBaja): string[] {
  const avisos: string[] = []
  for (const ubicacion of jornadas) {
    avisos.push(
      `Tiene una jornada abierta en ${ubicacion}: su teléfono va a poder subir lo pendiente, pero no va a poder operar. ` +
        'Para liberar la ubicación, liberá la jornada.',
    )
  }
  if (clientesAsignados > 0) {
    const cantidad = masDeLosContados
      ? `más de ${clientesAsignados} clientes asignados`
      : `${clientesAsignados} ${clientesAsignados === 1 ? 'cliente asignado' : 'clientes asignados'}`
    avisos.push(`Tiene ${cantidad}: quedan sin vendedor visible hasta que los reasignes.`)
  }
  return avisos
}

const MENSAJES_POR_CODIGO: Record<string, string> = {
  IDENTIDAD_AUTOBAJA: 'No podés darte de baja a vos mismo. Pedile a otro administrador que lo haga.',
  IDENTIDAD_ROL_INACTIVO: 'Ese rol está dado de baja y no se puede asignar. Elegí un rol activo o reactivá el rol.',
  IDENTIDAD_USUARIO_DUPLICADO: 'Ya existe un usuario con ese nombre de usuario. Elegí otro.',
  IDENTIDAD_SIN_ADMINISTRADOR:
    'No se guardó: la organización se quedaría sin nadie que administre usuarios y roles. Tiene que quedar al menos un usuario activo con ese permiso.',
  IDENTIDAD_NOMBRE_DE_ROL_INVALIDO: `El nombre del rol no puede estar vacío ni tener más de ${LARGO_MAXIMO_NOMBRE_DE_ROL} caracteres.`,
  IDENTIDAD_NOMBRE_DE_ROL_DUPLICADO: 'Ya existe un rol con ese nombre, aunque esté dado de baja. Elegí otro nombre.',
  IDENTIDAD_NOMBRE_DE_USUARIO_INVALIDO: `El nombre no puede estar vacío ni tener más de ${LARGO_MAXIMO_NOMBRE_DE_USUARIO} caracteres.`,
  IDENTIDAD_CONTRASENA_INCORRECTA: 'La contraseña actual no es correcta. Revisala y volvé a intentar.',
  IDENTIDAD_CONTRASENA_INVALIDA: `La contraseña nueva no sirve: tiene que tener al menos ${LARGO_MINIMO_DE_CONTRASENA} caracteres y no puede estar en blanco.`,
  IDENTIDAD_CONTRASENA_NUEVA_IGUAL_A_ACTUAL: 'La contraseña nueva tiene que ser distinta de la actual.',
  IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO: 'El tope tiene que estar entre 0 % y 100 %, con hasta cuatro decimales.',
  IDENTIDAD_TRANSICION_ESTADO_USUARIO_INVALIDA:
    'Ese usuario ya está en ese estado: alguien lo cambió antes. Actualizá la pantalla para ver cómo quedó.',
  VENDEDOR_INVALIDO:
    'Ese usuario no puede ser vendedor: tiene que estar activo, con un rol activo que permita vender o cobrar.',
  CLIENTE_CONSUMIDOR_FINAL_SIN_VENDEDOR: 'El consumidor final no se asigna a ningún vendedor: lo ven todos.',
  PERMISO_REQUERIDO: 'No tenés permiso para hacer esto.',
}

function mensajeDeRolConUsuarios(usuariosActivos: number | undefined): string {
  const cuantos =
    usuariosActivos === undefined
      ? 'usuarios activos'
      : `${usuariosActivos} ${usuariosActivos === 1 ? 'usuario activo' : 'usuarios activos'}`
  return `No se puede dar de baja este rol porque tiene ${cuantos}. Primero cambiales el rol y volvé a intentar.`
}

export interface ContextoDeError {
  /** Usuarios activos del rol, para explicar la baja rechazada. */
  usuariosActivos?: number
}

/**
 * Explicación en palabras simples de cada código. El bloqueo por intentos
 * (`IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS`) conserva el texto del servidor si lo trae, porque
 * incluye el momento del desbloqueo; si no, usa uno propio.
 */
export function mensajeDeErrorDeUsuarios(
  codigo: string | null,
  mensajeDelServidor: string,
  contexto: ContextoDeError = {},
): string {
  if (codigo === 'IDENTIDAD_ROL_CON_USUARIOS_ACTIVOS') return mensajeDeRolConUsuarios(contexto.usuariosActivos)
  if (codigo === 'IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS') {
    return (
      'Hiciste demasiados intentos con la contraseña. Esperá un rato o pedile a un administrador que te desbloquee. ' +
      mensajeDelServidor
    ).trim()
  }
  return (codigo !== null ? MENSAJES_POR_CODIGO[codigo] : undefined) ?? mensajeDelServidor
}
