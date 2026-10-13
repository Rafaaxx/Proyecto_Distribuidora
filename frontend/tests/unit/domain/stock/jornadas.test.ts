import { describe, expect, it } from 'vitest'

import type { CodigoPermiso } from '../../../../src/domain/identidad/permisos'
import {
  AMBITO_DE_LIBERACION,
  accionesDeJornada,
  esJornadaNoCerrada,
  esquemaApertura,
  esquemaLiberacion,
  etiquetaDeEstadoDeJornada,
  fusionarUsuarios,
  textoDeToma,
  ubicacionesParaAbrir,
} from '../../../../src/domain/stock/jornadas'

const UBICACION = '11111111-1111-4111-8111-111111111111'
const MOTIVO = '22222222-2222-4222-8222-222222222222'

const VENDEDOR: CodigoPermiso[] = ['TRANSFERIR_STOCK', 'ABRIR_JORNADA']
const SUPERVISORA: CodigoPermiso[] = ['TRANSFERIR_STOCK', 'ABRIR_JORNADA', 'RENDIR_JORNADA', 'LIBERAR_UBICACION']
const ADMINISTRACION: CodigoPermiso[] = ['TRANSFERIR_STOCK', 'RENDIR_JORNADA']
const CONSULTA: CodigoPermiso[] = ['VER_REPORTES']

const con = (permisos: readonly CodigoPermiso[]) => (permiso: CodigoPermiso) => permisos.includes(permiso)
const SIN_ACCIONES = { rendir: false, cerrar: false, liberar: false }

/** RUT-01, RUT-09, `01` §18: mismas reglas que el dominio del backend (`ABRIR_JORNADA`,
 * `RENDIR_JORNADA`, `LIBERAR_UBICACION`); ocultar no reemplaza al servidor (SEG-06). */
describe('accionesDeJornada', () => {
  it('un Vendedor no tiene ninguna acción sobre una jornada ABIERTA', () => {
    expect(accionesDeJornada('ABIERTA', con(VENDEDOR))).toEqual(SIN_ACCIONES)
  })

  it('una Supervisora rinde y libera una ABIERTA, y no cierra', () => {
    expect(accionesDeJornada('ABIERTA', con(SUPERVISORA))).toEqual({ rendir: true, cerrar: false, liberar: true })
  })

  it('Administración cierra una EN_RENDICION y no libera', () => {
    expect(accionesDeJornada('EN_RENDICION', con(ADMINISTRACION))).toEqual({
      rendir: false,
      cerrar: true,
      liberar: false,
    })
  })

  it('Administración rinde una ABIERTA y no la libera', () => {
    expect(accionesDeJornada('ABIERTA', con(ADMINISTRACION))).toEqual({ rendir: true, cerrar: false, liberar: false })
  })

  it('una Supervisora cierra y libera una EN_RENDICION, y no la rinde de nuevo', () => {
    expect(accionesDeJornada('EN_RENDICION', con(SUPERVISORA))).toEqual({ rendir: false, cerrar: true, liberar: true })
  })

  it.each(['CERRADA', 'LIBERADA'])('una jornada %s no ofrece acciones ni con todos los permisos', (estado) => {
    expect(accionesDeJornada(estado, con(SUPERVISORA))).toEqual(SIN_ACCIONES)
  })

  it('un estado desconocido no ofrece acciones', () => {
    expect(accionesDeJornada('OTRO', con(SUPERVISORA))).toEqual(SIN_ACCIONES)
  })

  it('sin permisos de jornada no hay acciones en ningún estado', () => {
    expect(accionesDeJornada('ABIERTA', con(CONSULTA))).toEqual(SIN_ACCIONES)
    expect(accionesDeJornada('EN_RENDICION', con(CONSULTA))).toEqual(SIN_ACCIONES)
  })
})

describe('esJornadaNoCerrada (INV-16)', () => {
  it('ABIERTA y EN_RENDICION son jornadas no cerradas', () => {
    expect(esJornadaNoCerrada('ABIERTA')).toBe(true)
    expect(esJornadaNoCerrada('EN_RENDICION')).toBe(true)
  })

  it('CERRADA y LIBERADA no lo son', () => {
    expect(esJornadaNoCerrada('CERRADA')).toBe(false)
    expect(esJornadaNoCerrada('LIBERADA')).toBe(false)
  })
})

describe('etiquetaDeEstadoDeJornada', () => {
  it.each([
    ['ABIERTA', 'Abierta'],
    ['EN_RENDICION', 'En rendición'],
    ['CERRADA', 'Cerrada'],
    ['LIBERADA', 'Liberada'],
  ])('%s se muestra como %s', (estado, etiqueta) => {
    expect(etiquetaDeEstadoDeJornada(estado)).toBe(etiqueta)
  })

  it('un estado desconocido se muestra tal cual', () => {
    expect(etiquetaDeEstadoDeJornada('RARO')).toBe('RARO')
  })
})

describe('ubicacionesParaAbrir (RUT-01, RUT-03)', () => {
  const base = { actualizado_en: '2026-01-01T00:00:00Z' }
  const camioneta1 = { ...base, id: 'c1', nombre: 'Camioneta 1', tipo: 'VEHICULO', requiere_toma: true, activo: true, jornada: { id: 'j', usuario_id: 'u', usuario_nombre: 'Juan', abierta_en: '2026-01-01T08:00:00Z', estado: 'ABIERTA' } }
  const camioneta2 = { ...base, id: 'c2', nombre: 'Camioneta 2', tipo: 'VEHICULO', requiere_toma: true, activo: true, jornada: null }
  const camioneta3 = { ...base, id: 'c3', nombre: 'Camioneta 3', tipo: 'VEHICULO', requiere_toma: true, activo: false }
  const deposito = { ...base, id: 'd1', nombre: 'Depósito central', tipo: 'DEPOSITO', requiere_toma: false, activo: true }

  it('ofrece solo la activa, con toma y libre', () => {
    const r = ubicacionesParaAbrir([camioneta1, camioneta2, camioneta3, deposito])
    expect(r.map((u) => u.nombre)).toEqual(['Camioneta 2'])
  })

  it('una ubicación EN_RENDICION sigue tomada y no se ofrece', () => {
    const enRendicion = { ...camioneta2, id: 'c4', jornada: { ...camioneta1.jornada, estado: 'EN_RENDICION' } }
    expect(ubicacionesParaAbrir([enRendicion])).toEqual([])
  })

  it('conserva el orden recibido y acepta una lista vacía', () => {
    const otra = { ...camioneta2, id: 'c5', nombre: 'Camioneta 5' }
    expect(ubicacionesParaAbrir([otra, camioneta2]).map((u) => u.id)).toEqual(['c5', 'c2'])
    expect(ubicacionesParaAbrir([])).toEqual([])
  })
})

describe('esquemaApertura', () => {
  it('acepta una ubicación elegida', () => {
    expect(esquemaApertura.safeParse({ ubicacion_id: UBICACION }).success).toBe(true)
  })

  it('rechaza una ubicación vacía con el mensaje de elegirla', () => {
    const r = esquemaApertura.safeParse({ ubicacion_id: '' })
    expect(r.success).toBe(false)
    expect(r.error?.issues[0]?.message).toBe('Elegí la ubicación que vas a tomar.')
  })
})

describe('esquemaLiberacion (RUT-09, D13)', () => {
  it('acepta motivo sin observación y con observación', () => {
    expect(esquemaLiberacion.safeParse({ motivo_id: MOTIVO, observacion: '' }).success).toBe(true)
    expect(esquemaLiberacion.safeParse({ motivo_id: MOTIVO, observacion: 'Se enfermó' }).success).toBe(true)
  })

  it('rechaza sin motivo', () => {
    const r = esquemaLiberacion.safeParse({ motivo_id: '', observacion: '' })
    expect(r.success).toBe(false)
    expect(r.error?.issues[0]?.message).toBe('Elegí el motivo de la liberación.')
  })

  it('acepta una observación de 500 caracteres y rechaza una de 501', () => {
    expect(esquemaLiberacion.safeParse({ motivo_id: MOTIVO, observacion: 'a'.repeat(500) }).success).toBe(true)
    expect(esquemaLiberacion.safeParse({ motivo_id: MOTIVO, observacion: 'a'.repeat(501) }).success).toBe(false)
  })

  it('el ámbito de los motivos es LIBERACION_JORNADA', () => {
    expect(AMBITO_DE_LIBERACION).toBe('LIBERACION_JORNADA')
  })
})

describe('textoDeToma (STK-09, RUT-01)', () => {
  it('nombra a quien la tiene y desde cuándo', () => {
    expect(textoDeToma({ usuario_nombre: 'Juan', abierta_en: '2026-04-10T11:00:00Z' })).toMatch(
      /^Tomada por Juan desde \d{2}\/\d{2}\/\d{4} \d{2}:\d{2}$/,
    )
  })

  it('sin nombre de usuario dice "un usuario"', () => {
    expect(textoDeToma({ usuario_nombre: null, abierta_en: '2026-04-10T11:00:00Z' })).toMatch(
      /^Tomada por un usuario desde /,
    )
  })
})

describe('fusionarUsuarios (filtro de usuario del listado)', () => {
  it('suma los usuarios nuevos, sin repetir, ordenados por nombre', () => {
    const conocidos = [{ id: 'b', nombre: 'Beto' }]
    const items = [
      { usuario_id: 'a', usuario_nombre: 'Ana' },
      { usuario_id: 'b', usuario_nombre: 'Beto' },
      { usuario_id: 'a', usuario_nombre: 'Ana' },
    ]
    expect(fusionarUsuarios(conocidos, items)).toEqual([
      { id: 'a', nombre: 'Ana' },
      { id: 'b', nombre: 'Beto' },
    ])
  })

  it('un usuario sin nombre se conserva con una etiqueta genérica', () => {
    expect(fusionarUsuarios([], [{ usuario_id: 'x', usuario_nombre: null }])).toEqual([{ id: 'x', nombre: 'Usuario sin nombre' }])
  })

  it('sin items devuelve los conocidos tal cual', () => {
    const conocidos = [{ id: 'a', nombre: 'Ana' }]
    expect(fusionarUsuarios(conocidos, [])).toEqual(conocidos)
  })
})
