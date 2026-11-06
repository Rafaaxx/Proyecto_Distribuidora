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
  AVISO_DE_RECHAZO_DE_ANULACION,
  TEXTO_DE_RECHAZO_GENERAL_DE_ANULACION,
  TEXTO_SIN_DETALLE,
  explicarEnvio,
  resumenDeObservaciones,
  textoDeObservacion,
  textoDeRechazo,
  textoDeObservacionDeAnulacion,
  textoDeRechazoDeAnulacion,
  AVISO_DE_RECHAZO_DE_COBRANZA,
  TEXTO_DE_RECHAZO_GENERAL_DE_COBRANZA,
  textoDeObservacionDeCobranza,
  textoDeRechazoDeCobranza,
  textoDeRechazoDeEntrega,
  type NombresLocales,
} from '../../../../src/domain/ruta/textosDeSincronizacion'
import type { ObservacionLocal } from '../../../../src/lib/dispositivo/db'

const FIXTURE = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../../shared/fixtures/sync/codigos-de-sincronizacion.json')
const CODIGOS = JSON.parse(readFileSync(FIXTURE, 'utf-8')) as {
  observaciones: string[]
  rechazos: string[]
  rechazos_de_anulacion: string[]
  observaciones_de_anulacion: string[]
  rechazos_de_cobranza: string[]
  rechazos_de_entrega: string[]
  observaciones_de_cobranza: string[]
}

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
    ['JORNADA_RENDIDA', null, 'Llegó cuando la jornada ya estaba rendida; no entra en el conteo.'],
    ['PRODUCTO_DESACTIVADO', { inactivo: 'PRODUCTO' }, 'Se vendió un producto o una presentación que en la oficina se desactivó.'],
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

/**
 * Change 22d, tarea 12.1 (D11, aprobados en 0.2; cita SYN-06, SYN-07): los rechazos y las
 * observaciones de una anulación, elegidos por tipo de operación.
 */
const DATOS_INVALIDOS = 'La anulación llegó con datos incompletos o inválidos.'

describe('textoDeRechazoDeAnulacion (D11, SYN-06)', () => {
  it.each(CODIGOS.rechazos_de_anulacion)('%s tiene texto aprobado para la anulación y se reconoce', (codigo) => {
    const rechazo = textoDeRechazoDeAnulacion(codigo)
    expect(rechazo.conocido).toBe(true)
    expect(rechazo.codigo).toBe(codigo)
    expect(rechazo.texto).not.toBe(TEXTO_DE_RECHAZO_GENERAL_DE_ANULACION)
    expect(rechazo.texto).not.toMatch(/venta llegó/i)
  })

  it.each([
    ['VENTA_INEXISTENTE', 'El sistema no tiene la venta que se quiso anular.'],
    ['VENTA_YA_ANULADA', 'La venta ya estaba anulada en el sistema.'],
    ['JORNADA_AJENA', 'La venta es de otra jornada.'],
    ['UBICACION_INACTIVA', 'La ubicación de la venta está dada de baja.'],
    ['MOTIVO_INVALIDO', 'El motivo de la anulación no es válido.'],
    ['DISPOSITIVO_REVOCADO', 'Este teléfono fue dado de baja; la anulación quedó para revisión.'],
    ['DEVOLUCION_INVALIDA', DATOS_INVALIDOS],
    ['CONSUMIDOR_FINAL_SIN_DEVOLUCION', DATOS_INVALIDOS],
    ['OBSERVACION_INVALIDA', DATOS_INVALIDOS],
    ['CONTENIDO_DE_COMANDO_INVALIDO', DATOS_INVALIDOS],
    ['MODO_NO_ADMITIDO_PARA_TIPO', DATOS_INVALIDOS],
    ['TIPO_DE_COMANDO_DESCONOCIDO', DATOS_INVALIDOS],
    ['VERSION_DE_COMANDO_SIN_HANDLER', DATOS_INVALIDOS],
    ['COMANDO_INCONSISTENTE', DATOS_INVALIDOS],
    ['JORNADA_INEXISTENTE', DATOS_INVALIDOS],
    ['JORNADA_REQUERIDA', DATOS_INVALIDOS],
  ])('%s -> %s', (codigo, esperado) => {
    expect(textoDeRechazoDeAnulacion(codigo).texto).toBe(esperado)
  })

  it('el mismo código dice una cosa para la venta y otra para la anulación', () => {
    expect(textoDeRechazo('JORNADA_AJENA').texto).toBe('La jornada de la venta es de otro usuario o de otro teléfono.')
    expect(textoDeRechazoDeAnulacion('JORNADA_AJENA').texto).toBe('La venta es de otra jornada.')
  })

  it('un código desconocido da el texto general de la anulación con el código', () => {
    expect(textoDeRechazoDeAnulacion('CODIGO_NUEVO')).toEqual({
      texto: TEXTO_DE_RECHAZO_GENERAL_DE_ANULACION,
      codigo: 'CODIGO_NUEVO',
      conocido: false,
    })
    expect(textoDeRechazoDeAnulacion(null)).toEqual({
      texto: TEXTO_DE_RECHAZO_GENERAL_DE_ANULACION,
      codigo: null,
      conocido: false,
    })
  })
})

describe('textoDeObservacionDeAnulacion (D11, SYN-07)', () => {
  it.each(CODIGOS.observaciones_de_anulacion)('%s tiene un texto propio de la anulación', (codigo) => {
    const texto = textoDeObservacionDeAnulacion(observacion(codigo), NOMBRES)
    expect(texto).not.toBe(textoDeObservacion(observacion('CODIGO_QUE_NO_EXISTE'), NOMBRES))
    expect(texto).not.toMatch(/llegó la venta/)
  })

  it.each([
    ['JORNADA_LIBERADA', 'La jornada había sido liberada cuando llegó la anulación.'],
    [
      'UBICACION_TOMADA_AL_SINCRONIZAR',
      'Cuando llegó la anulación, el vehículo estaba en rendición o en la jornada de otro vendedor.',
    ],
    ['PERMISO_REVOCADO', 'Cuando llegó la operación, tu usuario ya no tenía el permiso.'],
  ])('%s -> %s', (codigo, esperado) => {
    expect(textoDeObservacionDeAnulacion(observacion(codigo), NOMBRES)).toBe(esperado)
  })

  it('un código desconocido no rompe: texto general', () => {
    expect(textoDeObservacionDeAnulacion(observacion('NUEVO'), NOMBRES)).toBe(
      'El sistema anotó algo para que administración lo revise.',
    )
  })
})

describe('explicarEnvio de una anulación (D11; SYN-06, SYN-07)', () => {
  it('una anulación rechazada trae su texto, el código y «La venta sigue vigente…»', () => {
    expect(explicarEnvio('RECHAZADA', { error_codigo: 'VENTA_YA_ANULADA' }, NOMBRES, 'VENTA_ANULAR')).toEqual({
      tipo: 'rechazo',
      texto: 'La venta ya estaba anulada en el sistema.',
      codigo: 'VENTA_YA_ANULADA',
      aviso: AVISO_DE_RECHAZO_DE_ANULACION,
    })
    expect(AVISO_DE_RECHAZO_DE_ANULACION).toBe('La venta sigue vigente en el teléfono; avisá a administración.')
  })

  it('el mismo código sobre una venta mantiene el texto de la venta', () => {
    expect(explicarEnvio('RECHAZADA', { error_codigo: 'JORNADA_AJENA' }, NOMBRES, 'VENTA_CONFIRMAR')).toMatchObject({
      texto: 'La jornada de la venta es de otro usuario o de otro teléfono.',
      aviso: AVISO_DE_RECHAZO,
    })
  })

  it('una anulación con observaciones las traduce con los textos de la anulación', () => {
    expect(
      explicarEnvio(
        'CON_OBSERVACIONES',
        { error_codigo: null, observaciones: [observacion('JORNADA_LIBERADA')] },
        NOMBRES,
        'VENTA_ANULAR',
      ),
    ).toEqual({ tipo: 'observaciones', textos: ['La jornada había sido liberada cuando llegó la anulación.'] })
  })

  it('una anulación aceptada o sin enviar no explica nada', () => {
    expect(explicarEnvio('ACEPTADA', undefined, NOMBRES, 'VENTA_ANULAR')).toBeNull()
    expect(explicarEnvio('PENDIENTE', undefined, NOMBRES, 'VENTA_ANULAR')).toBeNull()
  })
})

/**
 * Change 23, tarea 9.1 (D11, aprobados en 0.2; SYN-06, SYN-07): rechazos y observaciones de la
 * cobranza, elegidos por el tipo de operación de la cola.
 */
const DATOS_INVALIDOS_COBRANZA = 'La cobranza llegó con datos incompletos o inválidos.'

describe('textoDeRechazoDeCobranza (D11, SYN-06)', () => {
  it.each(CODIGOS.rechazos_de_cobranza)('%s tiene texto aprobado para la cobranza y se reconoce', (codigo) => {
    const rechazo = textoDeRechazoDeCobranza(codigo)
    expect(rechazo.conocido).toBe(true)
    expect(rechazo.codigo).toBe(codigo)
    expect(rechazo.texto).not.toBe(TEXTO_DE_RECHAZO_GENERAL_DE_COBRANZA)
  })

  it.each([
    ['RECURSO_NO_ENCONTRADO', 'El sistema no tiene el cliente o el medio de pago de la cobranza.'],
    ['COBRANZA_DUPLICADA', 'El sistema ya tenía otra cobranza con el mismo identificador.'],
    ['JORNADA_AJENA', 'La cobranza es de otra jornada.'],
    ['DISPOSITIVO_REVOCADO', 'Este teléfono fue dado de baja; la cobranza quedó para revisión.'],
    ['MEDIOS_INVALIDOS', DATOS_INVALIDOS_COBRANZA],
    ['MEDIOS_NO_SUMAN_IMPORTE', DATOS_INVALIDOS_COBRANZA],
    ['IMPORTE_INVALIDO', DATOS_INVALIDOS_COBRANZA],
    ['JORNADA_REQUERIDA', DATOS_INVALIDOS_COBRANZA],
  ])('%s -> %s', (codigo, esperado) => {
    expect(textoDeRechazoDeCobranza(codigo).texto).toBe(esperado)
  })

  it('el mismo código dice una cosa para la venta y otra para la cobranza', () => {
    expect(textoDeRechazo('JORNADA_AJENA').texto).toBe('La jornada de la venta es de otro usuario o de otro teléfono.')
    expect(textoDeRechazoDeCobranza('JORNADA_AJENA').texto).toBe('La cobranza es de otra jornada.')
  })

  it('un código desconocido o nulo da el texto general de la cobranza', () => {
    expect(textoDeRechazoDeCobranza('CODIGO_NUEVO')).toEqual({
      texto: TEXTO_DE_RECHAZO_GENERAL_DE_COBRANZA,
      codigo: 'CODIGO_NUEVO',
      conocido: false,
    })
    expect(textoDeRechazoDeCobranza(null).conocido).toBe(false)
  })
})

describe('textoDeObservacionDeCobranza (D11, SYN-07)', () => {
  it.each(CODIGOS.observaciones_de_cobranza)('%s tiene un texto propio de la cobranza', (codigo) => {
    const texto = textoDeObservacionDeCobranza(observacion(codigo), NOMBRES)
    expect(texto).not.toBe(textoDeObservacionDeCobranza(observacion('NUEVO'), NOMBRES))
  })

  it.each([
    ['MEDIO_INACTIVO', { medio_pago_id: 'm-1' }, 'El medio Transferencia estaba dado de baja cuando llegó el cobro.'],
    ['MEDIO_INACTIVO', { nombre: 'Billetera' }, 'El medio Billetera estaba dado de baja cuando llegó el cobro.'],
    ['REFERENCIA_FALTANTE', { medio_pago_id: 'm-1' }, 'El cobro con Transferencia llegó sin la referencia que pide ese medio.'],
    ['PERMISO_REVOCADO', null, 'Cuando llegó la operación, tu usuario ya no tenía el permiso.'],
    ['JORNADA_LIBERADA', null, 'La jornada había sido liberada cuando llegó la cobranza.'],
    ['CLIENTE_NO_HABILITADO', null, 'El consumidor final no lleva cobranzas sueltas; administración la revisa.'],
  ])('%s -> %s', (codigo, detalle, esperado) => {
    expect(textoDeObservacionDeCobranza(observacion(codigo, detalle), NOMBRES)).toBe(esperado)
  })

  it('un código desconocido no rompe: texto general', () => {
    expect(textoDeObservacionDeCobranza(observacion('NUEVO'), NOMBRES)).toBe(
      'El sistema anotó algo para que administración lo revise.',
    )
  })
})

describe('explicarEnvio de una cobranza (D11; SYN-06, SYN-07)', () => {
  it('una cobranza rechazada trae su texto, el código y el aviso de que el teléfono ya no la descuenta', () => {
    expect(explicarEnvio('RECHAZADA', { error_codigo: 'RECURSO_NO_ENCONTRADO' }, NOMBRES, 'COBRANZA_REGISTRAR')).toEqual({
      tipo: 'rechazo',
      texto: 'El sistema no tiene el cliente o el medio de pago de la cobranza.',
      codigo: 'RECURSO_NO_ENCONTRADO',
      aviso: AVISO_DE_RECHAZO_DE_COBRANZA,
    })
    expect(AVISO_DE_RECHAZO_DE_COBRANZA).toBe(
      'El cobro no quedó registrado en el sistema y el teléfono ya no lo descuenta de la cuenta del cliente; avisá a administración.',
    )
  })

  it('una cobranza con observaciones las traduce con los textos de la cobranza', () => {
    expect(
      explicarEnvio(
        'CON_OBSERVACIONES',
        { error_codigo: null, observaciones: [observacion('MEDIO_INACTIVO', { nombre: 'Billetera' })] },
        NOMBRES,
        'COBRANZA_REGISTRAR',
      ),
    ).toEqual({ tipo: 'observaciones', textos: ['El medio Billetera estaba dado de baja cuando llegó el cobro.'] })
  })

  it('una cobranza aceptada o sin enviar no explica nada', () => {
    expect(explicarEnvio('ACEPTADA', undefined, NOMBRES, 'COBRANZA_REGISTRAR')).toBeNull()
    expect(explicarEnvio('PENDIENTE', undefined, NOMBRES, 'COBRANZA_REGISTRAR')).toBeNull()
  })
})

describe('JORNADA_RENDIDA (change 24, D7, D11; SYN-07)', () => {
  it.each([
    ['venta', textoDeObservacion],
    ['anulación', textoDeObservacionDeAnulacion],
    ['cobranza', textoDeObservacionDeCobranza],
  ])('la %s tardía lleva el mismo texto aprobado', (_operacion, traducir) => {
    expect(traducir(observacion('JORNADA_RENDIDA', { jornada_id: 'j-1', rendida_en: '2026-11-04T18:00:00+00:00' }), NOMBRES)).toBe(
      'Llegó cuando la jornada ya estaba rendida; no entra en el conteo.',
    )
  })
})

/**
 * Change 24, tarea 15.1 (D11, aprobados en 0.2; cita SYN-06, SYN-07): los rechazos de la entrega del
 * día, todos seguidos de «Avisá a tu supervisor.», se eligen por el tipo de operación de la cola.
 */
describe('explicarEnvio de la entrega del día (D11; SYN-06)', () => {
  it.each(CODIGOS.rechazos_de_entrega)('%s tiene texto aprobado para la entrega y se reconoce', (codigo) => {
    const r = textoDeRechazoDeEntrega(codigo)
    expect(r.conocido).toBe(true)
    expect(r.codigo).toBe(codigo)
    expect(r.texto).toMatch(/^La (jornada|entrega) /)
  })

  it.each([
    ['JORNADA_ESTADO_INVALIDO', 'La jornada ya no estaba abierta cuando llegó la entrega.'],
    ['JORNADA_YA_ENTREGADA', 'La jornada ya estaba entregada.'],
    ['JORNADA_AJENA', 'La entrega llegó con datos incompletos o inválidos.'],
    ['PERMISO_REQUERIDO', 'La entrega llegó con datos incompletos o inválidos.'],
    ['VERSION_DE_COMANDO_SIN_HANDLER', 'La entrega llegó con datos incompletos o inválidos.'],
  ])('%s dice «%s»', (codigo, esperado) => {
    expect(textoDeRechazoDeEntrega(codigo).texto).toBe(esperado)
  })

  it('un código que el teléfono no conoce da el texto general con su código', () => {
    expect(textoDeRechazoDeEntrega('CODIGO_NUEVO')).toEqual({
      texto: 'La entrega llegó con datos incompletos o inválidos.',
      codigo: 'CODIGO_NUEVO',
      conocido: false,
    })
  })

  it('una entrega RECHAZADA se explica con su texto, su código y «Avisá a tu supervisor.»', () => {
    const e = explicarEnvio('RECHAZADA', { error_codigo: 'JORNADA_YA_ENTREGADA' }, NOMBRES, 'JORNADA_ENTREGAR')
    expect(e).toEqual({
      tipo: 'rechazo',
      texto: 'La jornada ya estaba entregada.',
      codigo: 'JORNADA_YA_ENTREGADA',
      aviso: 'Avisá a tu supervisor.',
    })
  })

  it('una entrega sin error o aceptada no explica nada', () => {
    expect(explicarEnvio('ACEPTADA', undefined, NOMBRES, 'JORNADA_ENTREGAR')).toBeNull()
    expect(explicarEnvio('PENDIENTE', undefined, NOMBRES, 'JORNADA_ENTREGAR')).toBeNull()
  })
})
