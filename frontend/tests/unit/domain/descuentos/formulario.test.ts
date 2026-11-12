/**
 * Change 16, tarea 15.2: lo que el formulario de regla necesita del dominio para no llevar lógica en
 * los componentes: valores iniciales desde una regla guardada, alta y baja de alcances, fecha
 * local de un instante y el esquema de "Poner fin" (DSC-01, DSC-02, D15, D16). Nada pasa por
 * `number` salvo la prioridad.
 */

import { describe, expect, it } from 'vitest'

import {
  agregarAlcance,
  crearEsquemaFinDeVigencia,
  etiquetaDeValorDeAccion,
  formularioDesdeRegla,
  quitarAlcance,
  valorLocalDeFecha,
} from '../../../../src/domain/descuentos/formulario'
import type { ReglaPresentable } from '../../../../src/domain/descuentos/presentacion'

const MARCA = '11111111-1111-4111-8111-111111111111'
const CATEGORIA = '22222222-2222-4222-8222-222222222222'

function guardada(campos: Partial<ReglaPresentable & { nombre: string }> = {}): ReglaPresentable & { nombre: string } {
  return {
    nombre: 'Mayorista',
    tipo: 'VOLUMEN_OPERACION',
    medida: 'CAJAS_EQUIVALENTES',
    operador: 'GTE',
    umbral: '20.0000',
    accion_tipo: 'PORCENTAJE',
    accion_porcentaje: '0.050000',
    accion_importe: null,
    prioridad: 10,
    acumulable: false,
    vigencia_desde: null,
    vigencia_hasta: null,
    estado: 'BORRADOR',
    alcances: [],
    ...campos,
  }
}

describe('formularioDesdeRegla', () => {
  it('una regla de porcentaje vuelve a lo que la persona escribió: 0.050000 -> "5", umbral "20.0000" -> "20"', () => {
    expect(formularioDesdeRegla(guardada())).toEqual({
      nombre: 'Mayorista',
      tipo: 'VOLUMEN_OPERACION',
      medida: 'CAJAS_EQUIVALENTES',
      operador: 'GTE',
      umbral: '20',
      accion_tipo: 'PORCENTAJE',
      accion_valor: '5',
      prioridad: '10',
      acumulable: false,
      alcances: [],
      vigencia_desde: '',
      vigencia_hasta: '',
    })
  })

  it('un porcentaje con decimales y un importe fijo con centavos', () => {
    expect(formularioDesdeRegla(guardada({ accion_porcentaje: '0.125000' })).accion_valor).toBe('12.5')
    const fijo = formularioDesdeRegla(
      guardada({ accion_tipo: 'IMPORTE_FIJO', accion_porcentaje: null, accion_importe: '1000.50', umbral: '31250.0000' }),
    )
    expect(fijo.accion_valor).toBe('1000.5')
    expect(fijo.umbral).toBe('31250')
  })

  it('conserva los alcances (sin el nombre) y la vigencia como fecha local', () => {
    const formulario = formularioDesdeRegla(
      guardada({
        tipo: 'VOLUMEN_ALCANCE',
        alcances: [
          { tipo: 'MARCA', entidad_id: MARCA, nombre: 'Coca-Cola' },
          { tipo: 'CATEGORIA', entidad_id: CATEGORIA, nombre: 'Gaseosas' },
        ],
        vigencia_desde: '2026-10-10T12:00:00Z',
      }),
    )

    expect(formulario.alcances).toEqual([
      { tipo: 'MARCA', entidad_id: MARCA },
      { tipo: 'CATEGORIA', entidad_id: CATEGORIA },
    ])
    expect(formulario.vigencia_desde).toBe(valorLocalDeFecha('2026-10-10T12:00:00Z'))
    expect(formulario.vigencia_hasta).toBe('')
  })
})

describe('valorLocalDeFecha', () => {
  it('es la fecha y hora locales en el formato de datetime-local, y vuelve al mismo instante', () => {
    const iso = '2026-10-10T12:30:00Z'

    const local = valorLocalDeFecha(iso)

    expect(local).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
    expect(new Date(local).toISOString()).toBe('2026-10-10T12:30:00.000Z')
  })

  it('sin fecha es vacío', () => {
    expect(valorLocalDeFecha(null)).toBe('')
  })
})

describe('agregarAlcance y quitarAlcance (DSC-02)', () => {
  it('agrega un alcance nuevo al final', () => {
    const lista = agregarAlcance([{ tipo: 'MARCA', entidad_id: MARCA }], { tipo: 'CATEGORIA', entidad_id: CATEGORIA })

    expect(lista).toEqual([
      { tipo: 'MARCA', entidad_id: MARCA },
      { tipo: 'CATEGORIA', entidad_id: CATEGORIA },
    ])
  })

  it('no repite un alcance ni agrega uno sin entidad', () => {
    const base = [{ tipo: 'MARCA', entidad_id: MARCA }]

    expect(agregarAlcance(base, { tipo: 'MARCA', entidad_id: MARCA })).toEqual(base)
    expect(agregarAlcance(base, { tipo: 'CATEGORIA', entidad_id: '' })).toEqual(base)
  })

  it('la misma entidad con otro tipo es otro alcance', () => {
    expect(agregarAlcance([{ tipo: 'MARCA', entidad_id: MARCA }], { tipo: 'PRODUCTO', entidad_id: MARCA })).toHaveLength(2)
  })

  it('quita solo el alcance indicado', () => {
    const lista = [
      { tipo: 'MARCA', entidad_id: MARCA },
      { tipo: 'CATEGORIA', entidad_id: CATEGORIA },
    ]

    expect(quitarAlcance(lista, { tipo: 'MARCA', entidad_id: MARCA })).toEqual([{ tipo: 'CATEGORIA', entidad_id: CATEGORIA }])
    expect(quitarAlcance(lista, { tipo: 'PRODUCTO', entidad_id: MARCA })).toEqual(lista)
  })
})

describe('etiquetaDeValorDeAccion', () => {
  it('pide un porcentaje o un importe según la acción', () => {
    expect(etiquetaDeValorDeAccion('PORCENTAJE')).toBe('Porcentaje de descuento (%)')
    expect(etiquetaDeValorDeAccion('IMPORTE_FIJO')).toBe('Importe fijo ($)')
  })
})

describe('crearEsquemaFinDeVigencia (D15, D16)', () => {
  it('pide una fecha válida', () => {
    const esquema = crearEsquemaFinDeVigencia(null)

    expect(esquema.safeParse({ vigencia_hasta: '' }).success).toBe(false)
    expect(esquema.safeParse({ vigencia_hasta: 'mañana' }).success).toBe(false)
    expect(esquema.parse({ vigencia_hasta: '2026-12-31T18:00' }).vigencia_hasta).toBe(
      new Date('2026-12-31T18:00').toISOString(),
    )
  })

  it('debe ser posterior a la vigencia desde cuando la regla ya la tiene', () => {
    const esquema = crearEsquemaFinDeVigencia('2026-12-01T10:00:00Z')

    const antes = esquema.safeParse({ vigencia_hasta: '2026-11-01T10:00' })
    expect(antes.success).toBe(false)
    expect(antes.error?.issues[0]?.path).toEqual(['vigencia_hasta'])
    expect(esquema.safeParse({ vigencia_hasta: '2027-01-01T10:00' }).success).toBe(true)
  })
})
