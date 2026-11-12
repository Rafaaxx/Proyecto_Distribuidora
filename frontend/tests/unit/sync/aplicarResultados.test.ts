import 'fake-indexeddb/auto'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { leerSaldoConsiderado, leerStockDisponible } from '../../../src/areas/ruta/datos/disponibles'
import { baseLocal } from '../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../src/sync/aplicarBootstrap'
import { anularVentaLocal } from '../../../src/sync/anularVentaLocal'
import { aplicarResultados } from '../../../src/sync/aplicarResultados'
import { leerJornadaNoAbierta } from '../../../src/sync/estadoDeJornada'
import { registrarCobranzaLocal } from '../../../src/sync/registrarCobranzaLocal'
import { seleccionarCola } from '../../../src/sync/seleccionDeCola'
import { comandoDePrueba, sembrarComando } from '../utils/colaDePrueba'
import { bootstrapParaVender, IDS_DE_PRUEBA } from '../utils/datosParaVender'
import { sembrarVenta } from '../utils/sembrarVenta'

/**
 * Change 22b, tareas 3.1 y 3.2 (specs `sync/motor-de-sincronizacion`, «El resultado de cada
 * operación se escribe en el teléfono», y `sync/cola-local`, «Las operaciones locales no se
 * borran hasta su resultado» y «El saldo y el stock locales suman lo que hizo el teléfono»;
 * `design.md` D3, D4; cita INV-01, SYN-04, SYN-09, RUT-04, CRE-08).
 */
const AHORA = new Date('2026-11-01T12:00:00.000Z')

function resultado(operation_id: string, estado: string, error_codigo: string | null = null) {
  return { operation_id, estado, resultado: null, error_codigo }
}

async function contar() {
  return {
    ventas: await baseLocal.ventas.count(),
    cobranzas: await baseLocal.cobranzas.count(),
    movimientos: await baseLocal.movimientos_locales.count(),
    cola: await baseLocal.cola.count(),
  }
}

describe('aplicar los resultados del lote (tarea 3.1)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await sembrarComando(comandoDePrueba(1))
    await sembrarComando(comandoDePrueba(2))
    await sembrarComando(comandoDePrueba(3))
    await sembrarComando(comandoDePrueba(4))
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('por operation_id (no por posición): la cola toma estado, código y momento; la venta, su estado de envío', async () => {
    await aplicarResultados(
      [
        resultado('op-3', 'RECHAZADO', 'JORNADA_INEXISTENTE'),
        resultado('op-1', 'ACEPTADO'),
        resultado('op-2', 'ACEPTADO_CON_OBSERVACIONES'),
      ],
      AHORA,
    )

    const cola = await baseLocal.cola.orderBy('secuencia').toArray()
    expect(cola.map((c) => c.estado)).toEqual(['ACEPTADO', 'ACEPTADO_CON_OBSERVACIONES', 'RECHAZADO', 'PENDIENTE'])
    expect(cola[2]).toMatchObject({ error_codigo: 'JORNADA_INEXISTENTE', resultado_en: AHORA.toISOString() })
    expect(cola[0]?.error_codigo ?? null).toBeNull()
    const ventas = await baseLocal.ventas.orderBy('numero').toArray()
    expect(ventas.map((v) => v.estado_envio)).toEqual(['ACEPTADA', 'CON_OBSERVACIONES', 'RECHAZADA', 'PENDIENTE'])
  })

  it('ERROR_TRANSITORIO y lo no procesado quedan PENDIENTE', async () => {
    await aplicarResultados([resultado('op-1', 'ERROR_TRANSITORIO'), resultado('op-2', 'ACEPTADO')], AHORA)

    const cola = await baseLocal.cola.orderBy('secuencia').toArray()
    expect(cola.map((c) => c.estado)).toEqual(['PENDIENTE', 'ACEPTADO', 'PENDIENTE', 'PENDIENTE'])
    expect((await baseLocal.ventas.get('venta-1'))?.estado_envio).toBe('PENDIENTE')
  })

  it('un operation_id desconocido se ignora y se avisa en consola; los demás se aplican', async () => {
    const aviso = vi.spyOn(console, 'warn').mockImplementation(() => undefined)

    const resumen = await aplicarResultados(
      [resultado('op-desconocido', 'ACEPTADO'), resultado('op-1', 'ACEPTADO')],
      AHORA,
    )

    expect(aviso).toHaveBeenCalledOnce()
    expect(resumen).toEqual({ aplicados: 1, ignorados: 1 })
    expect((await baseLocal.cola.get(1))?.estado).toBe('ACEPTADO')
  })

  it('nada se borra: venta, cobranza, movimientos y comando siguen (SYN-09)', async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
    await sembrarVenta('a')
    const antes = await contar()

    await aplicarResultados([resultado('op-a', 'RECHAZADO', 'JORNADA_INEXISTENTE')], AHORA)

    expect(await contar()).toEqual(antes)
    expect((await baseLocal.ventas.get('venta-a'))?.estado_envio).toBe('RECHAZADA')
    expect(antes.movimientos).toBeGreaterThan(0)
  })

  it('es una sola transacción: con una falla después del primer resultado ninguno cambia (INV-01)', async () => {
    const original = baseLocal.ventas.where.bind(baseLocal.ventas)
    let llamadas = 0
    vi.spyOn(baseLocal.ventas, 'where').mockImplementation(((...args: Parameters<typeof original>) => {
      llamadas += 1
      if (llamadas === 2) throw new Error('falla inyectada')
      return original(...args)
    }) as typeof original)

    await expect(
      aplicarResultados([resultado('op-1', 'ACEPTADO'), resultado('op-2', 'ACEPTADO')], AHORA),
    ).rejects.toThrow('falla inyectada')

    vi.restoreAllMocks()
    expect((await baseLocal.cola.orderBy('secuencia').toArray()).map((c) => c.estado)).toEqual([
      'PENDIENTE',
      'PENDIENTE',
      'PENDIENTE',
      'PENDIENTE',
    ])
    expect((await baseLocal.ventas.get('venta-1'))?.estado_envio).toBe('PENDIENTE')
  })

  it('aplicar dos veces el mismo resultado deja lo mismo (el momento del primero se conserva)', async () => {
    await aplicarResultados([resultado('op-1', 'ACEPTADO')], AHORA)
    await aplicarResultados([resultado('op-1', 'ACEPTADO')], new Date('2026-11-01T13:00:00.000Z'))

    expect(await baseLocal.cola.get(1)).toMatchObject({ estado: 'ACEPTADO', resultado_en: AHORA.toISOString() })
  })
})

describe('las observaciones se guardan con el resultado (change 22c, tarea 5.1; INV-01, SYN-04, SYN-07)', () => {
  const OBSERVACIONES = [
    { codigo: 'STOCK_NEGATIVO', operacion_tipo: 'VENTA_CONFIRMAR', operacion_id: 'x', detalle: { producto_id: 'p1' } },
    { codigo: 'MEDIO_INACTIVO', operacion_tipo: 'VENTA_CONFIRMAR', operacion_id: 'x', detalle: null },
  ]

  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await sembrarComando(comandoDePrueba(1))
    await sembrarComando(comandoDePrueba(2))
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('«Venta con observaciones»: la fila de cola guarda las dos con el estado, en la misma escritura', async () => {
    await aplicarResultados(
      [{ ...resultado('op-1', 'ACEPTADO_CON_OBSERVACIONES'), observaciones: OBSERVACIONES }],
      AHORA,
    )

    expect(await baseLocal.cola.get(1)).toMatchObject({
      estado: 'ACEPTADO_CON_OBSERVACIONES',
      observaciones: OBSERVACIONES,
    })
  })

  it('«Falla al escribir los resultados»: con una falla inyectada no queda ninguna observación (INV-01)', async () => {
    const original = baseLocal.ventas.where.bind(baseLocal.ventas)
    let llamadas = 0
    vi.spyOn(baseLocal.ventas, 'where').mockImplementation(((...args: Parameters<typeof original>) => {
      llamadas += 1
      if (llamadas === 2) throw new Error('falla inyectada')
      return original(...args)
    }) as typeof original)

    await expect(
      aplicarResultados(
        [
          { ...resultado('op-1', 'ACEPTADO_CON_OBSERVACIONES'), observaciones: OBSERVACIONES },
          { ...resultado('op-2', 'ACEPTADO_CON_OBSERVACIONES'), observaciones: OBSERVACIONES },
        ],
        AHORA,
      ),
    ).rejects.toThrow('falla inyectada')

    vi.restoreAllMocks()
    const cola = await baseLocal.cola.orderBy('secuencia').toArray()
    expect(cola.map((c) => c.estado)).toEqual(['PENDIENTE', 'PENDIENTE'])
    expect(cola.every((c) => c.observaciones === undefined)).toBe(true)
  })

  it('«Respuesta sin observaciones»: sin la lista, observaciones queda sin dato; con lista vacía, vacía', async () => {
    await aplicarResultados([resultado('op-1', 'ACEPTADO')], AHORA)
    await aplicarResultados([{ ...resultado('op-2', 'ACEPTADO'), observaciones: [] }], AHORA)

    expect((await baseLocal.cola.get(1))?.observaciones).toBeUndefined()
    expect((await baseLocal.cola.get(2))?.observaciones).toEqual([])
  })

  it('un rechazo conserva su código y no inventa observaciones', async () => {
    await aplicarResultados([resultado('op-1', 'RECHAZADO', 'TOTALES_INCONSISTENTES')], AHORA)

    expect(await baseLocal.cola.get(1)).toMatchObject({ estado: 'RECHAZADO', error_codigo: 'TOTALES_INCONSISTENTES' })
    expect((await baseLocal.cola.get(1))?.observaciones).toBeUndefined()
  })

  it('el esquema de cola no cambia desde la v3 (D3); la base abre en la v5 (change 23)', async () => {
    expect(baseLocal.verno).toBe(5)
    expect(baseLocal.cola.schema.indexes.map((i) => i.name)).toEqual(['operation_id', 'estado'])
  })
})

describe('el stock y el saldo locales siguen contando la venta aceptada (tarea 3.2; D4)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
  })

  it('«Venta ya enviada»: después del ACEPTADO el stock (20 − 15 = 5) y el saldo se mantienen (RUT-04, CRE-08)', async () => {
    await sembrarVenta('a')
    const stockAntes = await leerStockDisponible(IDS_DE_PRUEBA.producto)
    const saldoAntes = await leerSaldoConsiderado(IDS_DE_PRUEBA.cliente)
    expect(stockAntes).toBe(5)

    await aplicarResultados([resultado('op-a', 'ACEPTADO')], AHORA)

    expect(await leerStockDisponible(IDS_DE_PRUEBA.producto)).toBe(5)
    expect(await leerSaldoConsiderado(IDS_DE_PRUEBA.cliente)).toBe(saldoAntes)
    const movimientos = await baseLocal.movimientos_locales.toArray()
    expect(movimientos.every((m) => m.estado_operacion === 'PENDIENTE')).toBe(true)
  })

  it('con la venta rechazada tampoco se tocan los movimientos locales (los concilia el 22c)', async () => {
    await sembrarVenta('b', { cajas: 1, unidades: 0 })
    expect(await leerStockDisponible(IDS_DE_PRUEBA.producto)).toBe(14)

    await aplicarResultados([resultado('op-b', 'RECHAZADO', 'JORNADA_INEXISTENTE')], AHORA)

    expect(await leerStockDisponible(IDS_DE_PRUEBA.producto)).toBe(14)
  })
})

/**
 * Change 22d, tarea 8.1 (spec `sync/motor-de-sincronizacion`, «El resultado de una anulación se
 * escribe en el teléfono», sus cinco escenarios; `design.md` D6; cita INV-01, INV-06, SYN-04,
 * SYN-06, SYN-07, SYN-09).
 */
describe('el resultado de una anulación se escribe en el teléfono (change 22d, tarea 8.1)', () => {
  const OBSERVACION_LIBERADA = {
    codigo: 'JORNADA_LIBERADA',
    operacion_tipo: 'VENTA',
    operacion_id: '0190a000-0000-7000-8000-0000000000aa',
    detalle: { jornada_id: 'j1' },
  }

  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    await aplicarResultados([resultado('op-a', 'ACEPTADO')], AHORA)
    await anularVentaLocal({
      ventaId: 'venta-a',
      motivo: { id: IDS_DE_PRUEBA.motivo, nombre: 'Error de carga' },
      observacion: null,
      devuelveDinero: null,
      operationId: 'op-anul-a',
      usuarioId: '00000000-0000-4000-8000-000000000001',
      dispositivoId: 'disp-1',
      ahora: AHORA,
      appVersion: '1.0.0',
    })
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('aceptada: la anulación y su comando quedan «Enviada» y la venta sigue como estaba (SYN-04, SYN-09)', async () => {
    await aplicarResultados([resultado('op-anul-a', 'ACEPTADO')], AHORA)

    expect((await baseLocal.anulaciones.get('venta-a'))?.estado_envio).toBe('ACEPTADA')
    expect(await baseLocal.cola.where('operation_id').equals('op-anul-a').first()).toMatchObject({
      estado: 'ACEPTADO',
      resultado_en: AHORA.toISOString(),
    })
    expect((await baseLocal.ventas.get('venta-a'))?.estado_envio).toBe('ACEPTADA')
  })

  it('con observaciones: la anulación queda «Con observaciones» y el comando guarda la observación con su detalle (SYN-07, RUT-09)', async () => {
    await aplicarResultados(
      [{ ...resultado('op-anul-a', 'ACEPTADO_CON_OBSERVACIONES'), observaciones: [OBSERVACION_LIBERADA] }],
      AHORA,
    )

    expect((await baseLocal.anulaciones.get('venta-a'))?.estado_envio).toBe('CON_OBSERVACIONES')
    const comando = await baseLocal.cola.where('operation_id').equals('op-anul-a').first()
    expect(comando?.observaciones).toEqual([OBSERVACION_LIBERADA])
    expect((await baseLocal.ventas.get('venta-a'))?.estado_envio).toBe('ACEPTADA')
  })

  it('rechazada: queda «Rechazada» con su código, sigue visible y no vuelve a la selección de envío (SYN-06, SYN-09)', async () => {
    await aplicarResultados([resultado('op-anul-a', 'RECHAZADO', 'VENTA_YA_ANULADA')], AHORA)

    expect((await baseLocal.anulaciones.get('venta-a'))?.estado_envio).toBe('RECHAZADA')
    expect(await baseLocal.cola.where('operation_id').equals('op-anul-a').first()).toMatchObject({
      estado: 'RECHAZADO',
      error_codigo: 'VENTA_YA_ANULADA',
    })
    expect((await baseLocal.ventas.get('venta-a'))?.estado_envio).toBe('ACEPTADA')
    const pendientes = await seleccionarCola('00000000-0000-4000-8000-000000000001', 'disp-1')
    expect(pendientes.map((c) => c.operation_id)).not.toContain('op-anul-a')
    expect(await baseLocal.anulaciones.count()).toBe(1)
  })

  it('una venta y su anulación en la misma respuesta cambian por su operation_id, cada una lo suyo', async () => {
    await sembrarVenta('b', { cajas: 1, unidades: 0 })

    await aplicarResultados([resultado('op-anul-a', 'ACEPTADO'), resultado('op-b', 'RECHAZADO', 'JORNADA_AJENA')], AHORA)

    expect((await baseLocal.anulaciones.get('venta-a'))?.estado_envio).toBe('ACEPTADA')
    expect((await baseLocal.ventas.get('venta-b'))?.estado_envio).toBe('RECHAZADA')
    expect((await baseLocal.ventas.get('venta-a'))?.estado_envio).toBe('ACEPTADA')
  })

  it('falla a mitad de la respuesta: ni la venta ni su anulación cambian y el próximo envío las manda otra vez (INV-01, INV-06)', async () => {
    await sembrarVenta('b', { cajas: 1, unidades: 0 })
    vi.spyOn(baseLocal.anulaciones, 'where').mockImplementation((() => {
      throw new Error('falla inyectada')
    }) as unknown as typeof baseLocal.anulaciones.where)

    await expect(
      aplicarResultados([resultado('op-b', 'ACEPTADO'), resultado('op-anul-a', 'ACEPTADO')], AHORA),
    ).rejects.toThrow('falla inyectada')

    vi.restoreAllMocks()
    expect((await baseLocal.ventas.get('venta-b'))?.estado_envio).toBe('PENDIENTE')
    expect((await baseLocal.anulaciones.get('venta-a'))?.estado_envio).toBe('PENDIENTE')
    expect((await baseLocal.cola.where('operation_id').equals('op-b').first())?.estado).toBe('PENDIENTE')
    expect((await baseLocal.cola.where('operation_id').equals('op-anul-a').first())?.estado).toBe('PENDIENTE')
  })

  it('doble envío: el mismo resultado otra vez no cambia la anulación ni su comando (INV-06, SYN-02)', async () => {
    await aplicarResultados([resultado('op-anul-a', 'ACEPTADO')], AHORA)
    const anulacion = await baseLocal.anulaciones.get('venta-a')
    const comando = await baseLocal.cola.where('operation_id').equals('op-anul-a').first()

    await aplicarResultados([resultado('op-anul-a', 'ACEPTADO')], new Date('2026-11-03T13:00:00.000Z'))

    expect(await baseLocal.anulaciones.get('venta-a')).toEqual(anulacion)
    expect(await baseLocal.cola.where('operation_id').equals('op-anul-a').first()).toEqual(comando)
  })

  it('una anulación rechazada deja de contar y la venta sigue descontando; la compensación es del 7.1 (D7)', async () => {
    expect(await leerStockDisponible(IDS_DE_PRUEBA.producto)).toBe(20)

    await aplicarResultados([resultado('op-anul-a', 'RECHAZADO', 'VENTA_YA_ANULADA')], AHORA)

    // La venta (1 caja = 6 unidades) sigue vigente en el servidor: se descuenta de nuevo.
    expect(await leerStockDisponible(IDS_DE_PRUEBA.producto)).toBe(14)
  })
})

describe('el resultado de una cobranza se escribe en el teléfono (change 23, tarea 6.1)', () => {
  const OBSERVACION_MEDIO = {
    codigo: 'MEDIO_INACTIVO',
    operacion_tipo: 'COBRANZA',
    operacion_id: '0190a000-0000-7000-8000-0000000000bb',
    detalle: { linea: 1 },
  }
  const OBSERVACION_LIBERADA = { ...OBSERVACION_MEDIO, codigo: 'JORNADA_LIBERADA', detalle: { jornada_id: 'j1' } }

  async function cobrar(sufijo: string, importe = '500.00') {
    return registrarCobranzaLocal({
      cobranzaId: `cobranza-${sufijo}`,
      operationId: `op-cob-${sufijo}`,
      clienteId: IDS_DE_PRUEBA.cliente,
      importe,
      medios: [{ medio_pago_id: IDS_DE_PRUEBA.efectivo, importe, referencia: null }],
      observacion: null,
      usuarioId: '00000000-0000-4000-8000-000000000001',
      dispositivoId: 'disp-1',
      ahora: AHORA,
      appVersion: '1.0.0',
    })
  }

  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
    await sembrarVenta('a', { cajas: 1, unidades: 0, cobro: '1000.00' })
    await cobrar('x')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('aceptada: la cobranza y su comando quedan «Enviada» y ninguna venta ni cobro de venta cambia (SYN-04, SYN-09)', async () => {
    const ventaAntes = await baseLocal.ventas.get('venta-a')

    await aplicarResultados([resultado('op-cob-x', 'ACEPTADO')], AHORA)

    expect((await baseLocal.cobranzas.get('cobranza-x'))?.estado_envio).toBe('ACEPTADA')
    expect(await baseLocal.cola.where('operation_id').equals('op-cob-x').first()).toMatchObject({
      estado: 'ACEPTADO',
      resultado_en: AHORA.toISOString(),
    })
    expect(await baseLocal.ventas.get('venta-a')).toEqual(ventaAntes)
    // El cobro en el momento de la venta no tiene estado de envío propio: sigue la suerte de su venta.
    expect(await baseLocal.cobranzas.where('venta_id').equals('venta-a').first()).not.toHaveProperty('estado_envio')
  })

  it('con observaciones: queda «Con observaciones» y el comando guarda la observación con su detalle (SYN-07)', async () => {
    await aplicarResultados(
      [{ ...resultado('op-cob-x', 'ACEPTADO_CON_OBSERVACIONES'), observaciones: [OBSERVACION_MEDIO] }],
      AHORA,
    )

    expect((await baseLocal.cobranzas.get('cobranza-x'))?.estado_envio).toBe('CON_OBSERVACIONES')
    expect((await baseLocal.cola.where('operation_id').equals('op-cob-x').first())?.observaciones).toEqual([OBSERVACION_MEDIO])
    expect((await baseLocal.ventas.get('venta-a'))?.estado_envio).toBe('PENDIENTE')
  })

  it('rechazada: queda «Rechazada» con su código, sigue visible y no vuelve a la selección de envío (SYN-06, SYN-09)', async () => {
    await aplicarResultados([resultado('op-cob-x', 'RECHAZADO', 'RECURSO_NO_ENCONTRADO')], AHORA)

    expect((await baseLocal.cobranzas.get('cobranza-x'))?.estado_envio).toBe('RECHAZADA')
    expect(await baseLocal.cola.where('operation_id').equals('op-cob-x').first()).toMatchObject({
      estado: 'RECHAZADO',
      error_codigo: 'RECURSO_NO_ENCONTRADO',
    })
    const pendientes = await seleccionarCola('00000000-0000-4000-8000-000000000001', 'disp-1')
    expect(pendientes.map((c) => c.operation_id)).not.toContain('op-cob-x')
    expect(await baseLocal.cobranzas.count()).toBe(2)
    expect(await baseLocal.movimientos_locales.where('operation_id').equals('op-cob-x').count()).toBe(1)
  })

  it('«JORNADA_LIBERADA» sobre la cobranza marca la jornada como liberada (RUT-09, SYN-07)', async () => {
    const sesion = await baseLocal.sesion.get('actual')

    await aplicarResultados(
      [{ ...resultado('op-cob-x', 'ACEPTADO_CON_OBSERVACIONES'), observaciones: [OBSERVACION_LIBERADA] }],
      AHORA,
    )

    const marca = await leerJornadaNoAbierta()
    expect(marca).toMatchObject({ estado: 'LIBERADA', jornada_id: sesion?.jornada.id })
  })

  it('falla a mitad de la respuesta: ni la cobranza ni la venta cambian y el próximo envío las manda otra vez (INV-01, INV-06)', async () => {
    vi.spyOn(baseLocal.cobranzas, 'where').mockImplementation((() => {
      throw new Error('falla inyectada')
    }) as unknown as typeof baseLocal.cobranzas.where)

    await expect(
      aplicarResultados([resultado('op-a', 'ACEPTADO'), resultado('op-cob-x', 'ACEPTADO')], AHORA),
    ).rejects.toThrow('falla inyectada')

    vi.restoreAllMocks()
    expect((await baseLocal.ventas.get('venta-a'))?.estado_envio).toBe('PENDIENTE')
    expect((await baseLocal.cobranzas.get('cobranza-x'))?.estado_envio).toBe('PENDIENTE')
    expect((await baseLocal.cola.where('operation_id').equals('op-a').first())?.estado).toBe('PENDIENTE')
    expect((await baseLocal.cola.where('operation_id').equals('op-cob-x').first())?.estado).toBe('PENDIENTE')
  })

  it('reenvío: el mismo resultado otra vez no cambia la cobranza, su comando ni sus observaciones (INV-06, SYN-02)', async () => {
    const respuesta = { ...resultado('op-cob-x', 'ACEPTADO_CON_OBSERVACIONES'), observaciones: [OBSERVACION_MEDIO] }
    await aplicarResultados([respuesta], AHORA)
    const cobranza = await baseLocal.cobranzas.get('cobranza-x')
    const comando = await baseLocal.cola.where('operation_id').equals('op-cob-x').first()

    await aplicarResultados([respuesta], new Date('2026-11-03T13:00:00.000Z'))

    expect(await baseLocal.cobranzas.get('cobranza-x')).toEqual(cobranza)
    expect(await baseLocal.cola.where('operation_id').equals('op-cob-x').first()).toEqual(comando)
  })

  it('una cobranza rechazada deja de contar en el saldo local y la aceptada no cambia nada (D6)', async () => {
    const antes = await leerSaldoConsiderado(IDS_DE_PRUEBA.cliente)

    await aplicarResultados([resultado('op-cob-x', 'ACEPTADO')], AHORA)
    expect(await leerSaldoConsiderado(IDS_DE_PRUEBA.cliente)).toBe(antes)

    await aplicarResultados([resultado('op-cob-x', 'RECHAZADO', 'RECURSO_NO_ENCONTRADO')], AHORA)
    // Sin la cobranza de 500,00 el saldo local sube 500,00.
    expect(Number(await leerSaldoConsiderado(IDS_DE_PRUEBA.cliente)) - Number(antes)).toBe(500)
  })
})
