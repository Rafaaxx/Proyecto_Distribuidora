/**
 * Change 22c, tarea 9.1 (D5; cita SYN-06, SYN-07): cada código del fixture compartido
 * `shared/fixtures/sync/codigos-de-sincronizacion.json` tiene su texto aprobado; el texto se arma
 * con el producto, el medio o el autorizador del detalle desde datos locales.
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import {
  AVISO_DE_RECHAZO,
  TEXTO_SIN_DETALLE,
  explicarEnvio,
  resumenDeObservaciones,
  textoDeObservacion,
  textoDeRechazo,
  type NombresLocales,
} from '../../../../src/domain/ruta/textosDeSincronizacion'
import type { ObservacionLocal } from '../../../../src/lib/dispositivo/db'

const FIXTURE = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../../shared/fixtures/sync/codigos-de-sincronizacion.json')
const CODIGOS = JSON.parse(readFileSync(FIXTURE, 'utf-8')) as { observaciones: string[]; rechazos: string[] }

const NOMBRES: NombresLocales = {
  productos: new Map([['p-1', 'Malbec 750']]),
  medios: new Map([['m-1', 'Transferencia']]),
  autorizadores: new Map([['a-1', 'Sup Uno']]),
}
const SIN_NOMBRES: NombresLocales = { productos: new Map(), medios: new Map(), autorizadores: new Map() }

function observacion(codigo: string, detalle: Record<string, unknown> | null = null): ObservacionLocal {
  return { codigo, operacion_tipo: 'VENTA', operacion_id: 'op-1', detalle }
}

describe('textoDeObservacion (D5, SYN-07)', () => {
  it.each(CODIGOS.observaciones)('%s tiene un texto propio (no el general)', (codigo) => {
    const texto = textoDeObservacion(observacion(codigo), NOMBRES)
    expect(texto.trim()).not.toBe('')
    expect(texto).not.toContain(codigo)
    expect(texto).not.toBe(textoDeObservacion(observacion('CODIGO_QUE_NO_EXISTE'), NOMBRES))
  })

  it.each([
    ['STOCK_NEGATIVO', { producto_id: 'p-1' }, 'Quedó stock negativo de Malbec 750.'],
    ['VENTA_SIN_COSTO', { producto_id: 'p-1' }, 'Malbec 750 no tenía costo; la línea quedó sin costo.'],
    ['MEDIO_INACTIVO', { medio_pago_id: 'm-1' }, 'El medio Transferencia estaba dado de baja cuando llegó el cobro.'],
    ['REFERENCIA_FALTANTE', { medio_pago_id: 'm-1' }, 'El cobro con Transferencia llegó sin la referencia que pide ese medio.'],
    ['AUTORIZACION_OFFLINE', { autorizador_id: 'a-1', tipo: 'DESCUENTO' }, 'Sup Uno autorizó el descuento sin señal.'],
    ['AUTORIZACION_OFFLINE', { autorizador_id: 'a-1', tipo: 'CREDITO' }, 'Sup Uno autorizó el exceso de crédito sin señal.'],
    ['LISTA_NO_VIGENTE', null, 'Los precios no eran los de la versión vigente de la lista en ese momento.'],
    ['JORNADA_LIBERADA', null, 'La jornada había sido liberada cuando llegó la venta.'],
  ])('%s arma el texto con los nombres locales', (codigo, detalle, esperado) => {
    expect(textoDeObservacion(observacion(codigo, detalle), NOMBRES)).toBe(esperado)
  })

  it('si el producto, el medio o el autorizador ya no están en la base local usa «un producto», «un medio» y «un supervisor»', () => {
    expect(textoDeObservacion(observacion('STOCK_NEGATIVO', { producto_id: 'borrado' }), SIN_NOMBRES)).toBe(
      'Quedó stock negativo de un producto.',
    )
    expect(textoDeObservacion(observacion('VENTA_SIN_COSTO', null), SIN_NOMBRES)).toBe(
      'Un producto no tenía costo; la línea quedó sin costo.',
    )
    expect(textoDeObservacion(observacion('MEDIO_INACTIVO', { medio_pago_id: 'borrado' }), SIN_NOMBRES)).toBe(
      'Un medio estaba dado de baja cuando llegó el cobro.',
    )
    expect(textoDeObservacion(observacion('REFERENCIA_FALTANTE', null), SIN_NOMBRES)).toBe(
      'El cobro con un medio llegó sin la referencia que pide ese medio.',
    )
    expect(textoDeObservacion(observacion('AUTORIZACION_OFFLINE', { tipo: 'CREDITO' }), SIN_NOMBRES)).toBe(
      'Un supervisor autorizó el exceso de crédito sin señal.',
    )
  })

  it('un código de observación desconocido no rompe: texto general', () => {
    expect(textoDeObservacion(observacion('NUEVO'), NOMBRES)).toBe('El sistema anotó algo para que administración lo revise.')
  })
})

describe('textoDeRechazo (D5, SYN-06)', () => {
  it.each(CODIGOS.rechazos)('%s tiene texto aprobado y se reconoce', (codigo) => {
    const rechazo = textoDeRechazo(codigo)
    expect(rechazo.conocido).toBe(true)
    expect(rechazo.texto).not.toBe('El sistema no aceptó esta venta.')
    expect(rechazo.codigo).toBe(codigo)
  })

  it.each([
    ['JORNADA_INEXISTENTE', 'La jornada de la venta no existe en el sistema.'],
    ['JORNADA_REQUERIDA', 'La venta llegó sin jornada.'],
    ['JORNADA_AJENA', 'La jornada de la venta es de otro usuario o de otro teléfono.'],
    ['DISPOSITIVO_REVOCADO', 'Este teléfono fue dado de baja; la venta quedó para revisión.'],
    ['COMANDO_INCONSISTENTE', 'El sistema ya tenía otra venta con el mismo identificador o número.'],
    ['VENTA_DUPLICADA', 'El sistema ya tenía otra venta con el mismo identificador o número.'],
    ['NUMERO_DUPLICADO', 'El sistema ya tenía otra venta con el mismo identificador o número.'],
    ['TOTALES_INCONSISTENTES', 'Los importes de la venta no cierran con el cálculo del sistema.'],
    ['CREDITO_INCONSISTENTE', 'La evaluación de crédito del teléfono no es coherente.'],
    ['VENTA_SIN_LINEAS', 'La venta llegó con datos incompletos o inválidos.'],
    ['CONTENIDO_DE_COMANDO_INVALIDO', 'La venta llegó con datos incompletos o inválidos.'],
    ['MODO_NO_ADMITIDO_PARA_TIPO', 'La venta llegó con datos incompletos o inválidos.'],
  ])('%s -> %s', (codigo, esperado) => {
    expect(textoDeRechazo(codigo).texto).toBe(esperado)
  })

  it('un código desconocido da «El sistema no aceptó esta venta.» con el código', () => {
    expect(textoDeRechazo('CODIGO_NUEVO')).toEqual({
      texto: 'El sistema no aceptó esta venta.',
      codigo: 'CODIGO_NUEVO',
      conocido: false,
    })
  })

  it('sin código guardado da el texto general y ningún código', () => {
    expect(textoDeRechazo(null)).toEqual({ texto: 'El sistema no aceptó esta venta.', codigo: null, conocido: false })
  })
})

describe('resumenDeObservaciones (D4)', () => {
  it('con una sola observación no dice «más»', () => {
    expect(resumenDeObservaciones(['A.'])).toEqual({ primera: 'A.', mas: null })
  })
  it('con dos dice «1 más» y con cuatro «3 más»', () => {
    expect(resumenDeObservaciones(['A.', 'B.'])).toEqual({ primera: 'A.', mas: '1 más' })
    expect(resumenDeObservaciones(['A.', 'B.', 'C.', 'D.'])).toEqual({ primera: 'A.', mas: '3 más' })
  })
  it('sin observaciones no hay resumen', () => {
    expect(resumenDeObservaciones([])).toBeNull()
  })
})

describe('explicarEnvio (D3, D4)', () => {
  it('una «Con observaciones» con la lista guardada explica todas, en orden', () => {
    const e = explicarEnvio('CON_OBSERVACIONES', {
      error_codigo: null,
      observaciones: [observacion('LISTA_NO_VIGENTE'), observacion('STOCK_NEGATIVO', { producto_id: 'p-1' })],
    }, NOMBRES)
    expect(e).toEqual({
      tipo: 'observaciones',
      textos: [
        'Los precios no eran los de la versión vigente de la lista en ese momento.',
        'Quedó stock negativo de Malbec 750.',
      ],
    })
  })

  it('una «Con observaciones» sin la lista (aceptada antes del 22c) dice que el detalle no está en el teléfono', () => {
    expect(explicarEnvio('CON_OBSERVACIONES', { error_codigo: null }, NOMBRES)).toEqual({
      tipo: 'sin_detalle',
      texto: TEXTO_SIN_DETALLE,
    })
    expect(explicarEnvio('CON_OBSERVACIONES', undefined, NOMBRES)).toEqual({ tipo: 'sin_detalle', texto: TEXTO_SIN_DETALLE })
    expect(TEXTO_SIN_DETALLE).toBe('El detalle no está en el teléfono; consultalo con administración.')
  })

  it('una rechazada trae texto, código y el aviso de que sigue guardada', () => {
    expect(explicarEnvio('RECHAZADA', { error_codigo: 'TOTALES_INCONSISTENTES' }, NOMBRES)).toEqual({
      tipo: 'rechazo',
      texto: 'Los importes de la venta no cierran con el cálculo del sistema.',
      codigo: 'TOTALES_INCONSISTENTES',
      aviso: AVISO_DE_RECHAZO,
    })
    expect(AVISO_DE_RECHAZO).toBe('Sigue guardada en el teléfono; avisá a administración.')
  })

  it('una «Enviada» (o sin enviar) no explica nada', () => {
    expect(explicarEnvio('ACEPTADA', { error_codigo: null, observaciones: [] }, NOMBRES)).toBeNull()
    expect(explicarEnvio('PENDIENTE', undefined, NOMBRES)).toBeNull()
  })
})
