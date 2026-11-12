import { z } from 'zod'

import { formatearFechaHora } from '../../lib/fecha'
import type { CodigoPermiso } from '../identidad/permisos'

/**
 * Jornadas (change 15, grupo 13; `design.md` D4, D13, D15, D16). Lógica pura: qué acciones
 * ofrece una jornada según su estado y los permisos de quien mira (mismas reglas que el dominio
 * del backend), qué ubicaciones se pueden tomar y la validación de la apertura y de la
 * liberación. Ocultar una acción es una comodidad de la interfaz: el servidor valida siempre
 * (SEG-06).
 */

/** Ámbito de los motivos de liberación (D13, `03` §4). */
export const AMBITO_DE_LIBERACION = 'LIBERACION_JORNADA'

export const ESTADOS_DE_JORNADA = ['ABIERTA', 'EN_RENDICION', 'CERRADA', 'LIBERADA'] as const
export type EstadoDeJornada = (typeof ESTADOS_DE_JORNADA)[number]

const ETIQUETAS_DE_ESTADO: Record<EstadoDeJornada, string> = {
  ABIERTA: 'Abierta',
  EN_RENDICION: 'En rendición',
  CERRADA: 'Cerrada',
  LIBERADA: 'Liberada',
}

/** El estado en palabras; uno desconocido se muestra tal cual. */
export function etiquetaDeEstadoDeJornada(estado: string): string {
  return estado in ETIQUETAS_DE_ESTADO ? ETIQUETAS_DE_ESTADO[estado as EstadoDeJornada] : estado
}

/** INV-16: "no cerrada" es `ABIERTA` o `EN_RENDICION`. */
export function esJornadaNoCerrada(estado: string): boolean {
  return estado === 'ABIERTA' || estado === 'EN_RENDICION'
}

/** Quien tiene alguno de estos permisos lee las jornadas de la organización (D15). */
export const PERMISOS_DE_LECTURA_DE_JORNADAS: readonly CodigoPermiso[] = [
  'ABRIR_JORNADA',
  'RENDIR_JORNADA',
  'LIBERAR_UBICACION',
]

export interface AccionesDeJornada {
  rendir: boolean
  cerrar: boolean
  liberar: boolean
}

/**
 * Acciones de una jornada: "Rendir" con `RENDIR_JORNADA` sobre `ABIERTA`; "Cerrar" con
 * `RENDIR_JORNADA` sobre `EN_RENDICION`; "Liberar" con `LIBERAR_UBICACION` sobre las dos.
 * Ninguna sobre `CERRADA` o `LIBERADA` (TR-06).
 */
export function accionesDeJornada(estado: string, tiene: (permiso: CodigoPermiso) => boolean): AccionesDeJornada {
  const rinde = tiene('RENDIR_JORNADA')
  return {
    rendir: estado === 'ABIERTA' && rinde,
    cerrar: estado === 'EN_RENDICION' && rinde,
    liberar: esJornadaNoCerrada(estado) && tiene('LIBERAR_UBICACION'),
  }
}

export interface UbicacionTomable {
  activo: boolean
  requiere_toma: boolean
  jornada?: { estado: string } | null | undefined
}

/** Ubicaciones que se pueden elegir al abrir: activas, con toma y sin jornada no cerrada. */
export function ubicacionesParaAbrir<T extends UbicacionTomable>(ubicaciones: readonly T[]): T[] {
  return ubicaciones.filter((u) => u.activo && u.requiere_toma && !u.jornada)
}

export const LIMITE_DE_OBSERVACION = 500

export const esquemaApertura = z.object({
  ubicacion_id: z.string().min(1, 'Elegí la ubicación que vas a tomar.'),
})
export type DatosDeApertura = z.infer<typeof esquemaApertura>

export const esquemaLiberacion = z.object({
  motivo_id: z.string().min(1, 'Elegí el motivo de la liberación.'),
  observacion: z.string().max(LIMITE_DE_OBSERVACION, `La observación admite hasta ${LIMITE_DE_OBSERVACION} caracteres.`),
})
export type DatosDeLiberacion = z.infer<typeof esquemaLiberacion>

/** "Tomada por Juan desde 10/04/2026 08:00": la marca de una ubicación con jornada no cerrada (STK-09). */
export function textoDeToma(toma: { usuario_nombre: string | null; abierta_en: string }): string {
  return `Tomada por ${toma.usuario_nombre ?? 'un usuario'} desde ${formatearFechaHora(toma.abierta_en)}`
}

export interface UsuarioConocido {
  id: string
  nombre: string
}

/**
 * Usuarios que aparecen en las jornadas vistas: el filtro de usuario del listado se arma con ellos
 * (la lista de usuarios exige `ADMIN_USUARIOS`, que Supervisión no tiene). Sin repetir, por nombre.
 */
export function fusionarUsuarios(
  conocidos: readonly UsuarioConocido[],
  items: readonly { usuario_id: string; usuario_nombre: string | null }[],
): UsuarioConocido[] {
  const porId = new Map(conocidos.map((u) => [u.id, u]))
  for (const item of items) {
    if (!porId.has(item.usuario_id)) {
      porId.set(item.usuario_id, { id: item.usuario_id, nombre: item.usuario_nombre ?? 'Usuario sin nombre' })
    }
  }
  return [...porId.values()].sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'))
}
