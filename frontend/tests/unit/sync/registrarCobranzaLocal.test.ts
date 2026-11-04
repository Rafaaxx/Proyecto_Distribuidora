import 'fake-indexeddb/auto'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { leerSaldoConsiderado } from '../../../src/areas/ruta/datos/disponibles'
import { baseLocal } from '../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../src/sync/aplicarBootstrap'
import { CLAVE_ULTIMA_SECUENCIA } from '../../../src/sync/confirmarVentaLocal'
import { registrarCobranzaLocal, type EntradaDeCobranzaConfirmada } from '../../../src/sync/registrarCobranzaLocal'
import { ID } from '../utils/bootstrapDePrueba'
import { bootstrapParaVender, IDS_DE_PRUEBA } from '../utils/datosParaVender'
import { sembrarVenta } from '../utils/sembrarVenta'

/**
 * Change 23, tarea 4.2 (spec `sync/cola-local`, «Registrar una cobranza local es una sola
 * transacción», sus cuatro escenarios; `design.md` D1, D5; cita INV-01, INV-06, SYN-01, SYN-02,
 * SYN-03, COB-01, COB-04). El cliente de prueba (Almacén Uno) debe $1.500,50.
 */
const USUARIO = ID(1)
const AHORA = new Date('2026-11-03T12:30:00.000Z')
const TRANSFERENCIA = ID(23)
const JORNADA = ID(2)

function bootstrapConTransferencia() {
  return bootstrapParaVender((b) => {
    b.sesion.permisos = ['VENDER', 'REGISTRAR_COBRANZA']
    b.catalogos.medios_pago.push({ id: TRANSFERENCIA, nombre: 'Transferencia', requiere_referencia: true })
  })
}

function entrada(sufijo: string, cambios: Partial<EntradaDeCobranzaConfirmada> = {}): EntradaDeCobranzaConfirmada {
  return {
    cobranzaId: `cobranza-${sufijo}`,
    operationId: `op-cob-${sufijo}`,
    clienteId: IDS_DE_PRUEBA.cliente,
    importe: '500.50',
    medios: [
      { medio_pago_id: IDS_DE_PRUEBA.efectivo, importe: '300.00', referencia: null },
      { medio_pago_id: TRANSFERENCIA, importe: '200.50', referencia: '0042' },
    ],
    observacion: null,
    usuarioId: USUARIO,
    dispositivoId: 'disp-1',
    ahora: AHORA,
    appVersion: '1.0.0',
    ...cambios,
  }
}

async function contar() {
  return {
    cobranzas: await baseLocal.cobranzas.count(),
    movimientos: await baseLocal.movimientos_locales.count(),
    cola: await baseLocal.cola.count(),
    ultimaSecuencia: (await baseLocal.meta.get(CLAVE_ULTIMA_SECUENCIA))?.valor,
  }
}

describe('registrar una cobranza local es una sola transacción (change 23, tarea 4.2)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapConTransferencia())
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('escribe la cobranza «Sin enviar», un crédito al cliente y el comando COBRANZA_REGISTRAR OFFLINE con la secuencia 8 (COB-01, COB-04, SYN-01)', async () => {
    await baseLocal.meta.put({ clave: CLAVE_ULTIMA_SECUENCIA, valor: '7' })

    const r = await registrarCobranzaLocal(entrada('a', { observacion: 'Pago de la cuota' }))

    expect(r.repetida).toBe(false)
    expect(r.cobranza).toMatchObject({
      cobranza_id: 'cobranza-a',
      venta_id: null,
      operation_id: 'op-cob-a',
      jornada_id: JORNADA,
      origen: 'INDEPENDIENTE',
      cliente_id: IDS_DE_PRUEBA.cliente,
      estado_envio: 'PENDIENTE',
      total: '500.50',
      observacion: 'Pago de la cuota',
      occurred_at: AHORA.toISOString(),
    })
    expect(await baseLocal.cobranzas.get('cobranza-a')).toEqual(r.cobranza)
    expect(r.comando).toMatchObject({ secuencia: 8, operation_id: 'op-cob-a', estado: 'PENDIENTE' })
    expect(r.comando.sobre).toMatchObject({
      tipo: 'COBRANZA_REGISTRAR',
      version: 1,
      modo: 'OFFLINE',
      secuencia: 8,
      usuario_id: USUARIO,
      dispositivo_id: 'disp-1',
      jornada_id: JORNADA,
      contenido: {
        cobranza_id: 'cobranza-a',
        cliente_id: IDS_DE_PRUEBA.cliente,
        importe: '500.50',
        observacion: 'Pago de la cuota',
        medios: [
          { medio_pago_id: IDS_DE_PRUEBA.efectivo, importe: '300.00', referencia: null },
          { medio_pago_id: TRANSFERENCIA, importe: '200.50', referencia: '0042' },
        ],
      },
    })
    expect(r.comando.sobre.contenido).not.toHaveProperty('credenciales')
    expect((await baseLocal.meta.get(CLAVE_ULTIMA_SECUENCIA))?.valor).toBe('8')

    const movimientos = await baseLocal.movimientos_locales.where('operation_id').equals('op-cob-a').toArray()
    expect(movimientos).toHaveLength(1)
    expect(movimientos[0]).toMatchObject({
      tipo: 'COBRANZA_CREDITO',
      cliente_id: IDS_DE_PRUEBA.cliente,
      jornada_id: JORNADA,
      importe: '500.50',
      producto_id: null,
      cantidad_base: null,
    })
    // El saldo local baja enseguida: $1.500,50 - $500,50 (CRE-08, COB-04).
    expect(await leerSaldoConsiderado(IDS_DE_PRUEBA.cliente)).toBe('1000.00')
  })

  it('congela el nombre del cliente y de los medios para el detalle (D5)', async () => {
    const r = await registrarCobranzaLocal(entrada('a'))

    expect(r.cobranza.cliente_nombre).toBe('Almacén Uno')
    expect(r.cobranza.medios_nombres).toEqual([
      { medio_pago_id: IDS_DE_PRUEBA.efectivo, nombre: 'Efectivo' },
      { medio_pago_id: TRANSFERENCIA, nombre: 'Transferencia' },
    ])
  })

  it('sin antecedentes la primera secuencia es la 1; una segunda cobranza, la 2, con otro movimiento (SYN-03)', async () => {
    const primera = await registrarCobranzaLocal(entrada('a', { importe: '100.00', medios: [{ medio_pago_id: IDS_DE_PRUEBA.efectivo, importe: '100.00', referencia: null }] }))
    const segunda = await registrarCobranzaLocal(entrada('b', { importe: '50.00', medios: [{ medio_pago_id: IDS_DE_PRUEBA.efectivo, importe: '50.00', referencia: null }] }))

    expect([primera.comando.secuencia, segunda.comando.secuencia]).toEqual([1, 2])
    expect(await leerSaldoConsiderado(IDS_DE_PRUEBA.cliente)).toBe('1350.50')
  })

  it('falla a mitad: no queda cobranza, movimiento ni comando y la secuencia no avanza (INV-01)', async () => {
    await baseLocal.meta.put({ clave: CLAVE_ULTIMA_SECUENCIA, valor: '7' })
    const antes = await contar()
    vi.spyOn(baseLocal.cola, 'add').mockRejectedValue(new Error('falla inyectada'))

    await expect(registrarCobranzaLocal(entrada('a'))).rejects.toThrow('falla inyectada')

    vi.restoreAllMocks()
    expect(await contar()).toEqual(antes)
    expect(antes.ultimaSecuencia).toBe('7')
    expect(await baseLocal.cobranzas.get('cobranza-a')).toBeUndefined()
  })

  it('otra falla (en el movimiento) tampoco deja la cobranza escrita (INV-01)', async () => {
    const antes = await contar()
    vi.spyOn(baseLocal.movimientos_locales, 'add').mockRejectedValue(new Error('falla en el movimiento'))

    await expect(registrarCobranzaLocal(entrada('a'))).rejects.toThrow('falla en el movimiento')

    vi.restoreAllMocks()
    expect(await contar()).toEqual(antes)
  })

  it('reconfirmar la misma cobranza devuelve la existente sin escribir nada (INV-06, SYN-02)', async () => {
    const primera = await registrarCobranzaLocal(entrada('a'))
    const antes = await contar()

    const otra = await registrarCobranzaLocal(entrada('a', { operationId: 'op-cob-distinto', importe: '999.00' }))

    expect(otra.repetida).toBe(true)
    expect(otra.cobranza).toEqual(primera.cobranza)
    expect(otra.comando).toEqual(primera.comando)
    expect(await contar()).toEqual(antes)
  })

  it('detrás de una venta «Sin enviar»: venta 1, cobranza 2 y se envían en ese orden (SYN-03)', async () => {
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    expect((await baseLocal.cola.get(1))?.estado).toBe('PENDIENTE')

    const r = await registrarCobranzaLocal(entrada('a'))

    expect(r.comando.secuencia).toBe(2)
    const pendientes = (await baseLocal.cola.where('estado').equals('PENDIENTE').toArray()).sort(
      (x, y) => x.secuencia - y.secuencia,
    )
    expect(pendientes.map((c) => [c.secuencia, c.sobre.tipo])).toEqual([
      [1, 'VENTA_CONFIRMAR'],
      [2, 'COBRANZA_REGISTRAR'],
    ])
  })

  it('sin sesión local no se puede cobrar y no se escribe nada', async () => {
    await baseLocal.sesion.clear()
    const antes = await contar()

    await expect(registrarCobranzaLocal(entrada('a'))).rejects.toThrow('No hay sesión local')

    expect(await contar()).toEqual(antes)
  })
})
