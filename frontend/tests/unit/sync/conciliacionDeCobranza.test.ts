import 'fake-indexeddb/auto'

import { beforeEach, describe, expect, it } from 'vitest'

import { leerSaldoConsiderado } from '../../../src/areas/ruta/datos/disponibles'
import { baseLocal } from '../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../src/sync/aplicarBootstrap'
import { registrarCobranzaLocal } from '../../../src/sync/registrarCobranzaLocal'
import { ID } from '../utils/bootstrapDePrueba'
import { bootstrapParaVender, IDS_DE_PRUEBA } from '../utils/datosParaVender'
import { sembrarVenta } from '../utils/sembrarVenta'

/**
 * Change 23, tarea 5.1 (spec `sync/cola-local`, «La cobranza local cuenta en el saldo local»;
 * D6; CRE-08, COB-04, SYN-06, SYN-11, INV-06): la conciliación leída de Dexie. El cliente de
 * prueba (Almacén Uno) debe $1.500,50 en el bootstrap.
 */
const AHORA = new Date('2026-11-03T12:30:00.000Z')

async function cobrar(sufijo: string, importe: string) {
  return registrarCobranzaLocal({
    cobranzaId: `cobranza-${sufijo}`,
    operationId: `op-cob-${sufijo}`,
    clienteId: IDS_DE_PRUEBA.cliente,
    importe,
    medios: [{ medio_pago_id: IDS_DE_PRUEBA.efectivo, importe, referencia: null }],
    observacion: null,
    usuarioId: ID(1),
    dispositivoId: 'disp-1',
    ahora: AHORA,
    appVersion: '1.0.0',
  })
}

describe('la cobranza independiente en la conciliación leída de Dexie (change 23, tarea 5.1)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
  })

  it('sin enviar cuenta: 1.500,50 - 500,00 = 1.000,50 (COB-04)', async () => {
    await cobrar('a', '500.00')

    expect(await leerSaldoConsiderado(IDS_DE_PRUEBA.cliente)).toBe('1000.50')
  })

  it('rechazada deja de contar y el saldo vuelve al del bootstrap (SYN-06)', async () => {
    await cobrar('a', '500.00')
    await baseLocal.cola.where('operation_id').equals('op-cob-a').modify({ estado: 'RECHAZADO', error_codigo: 'RECURSO_NO_ENCONTRADO' })

    expect(await leerSaldoConsiderado(IDS_DE_PRUEBA.cliente)).toBe('1500.50')
  })

  it('un bootstrap que ya la incluye (marca = su secuencia) no la cuenta dos veces (INV-06, SYN-11)', async () => {
    await cobrar('a', '500.00')
    const nuevo = bootstrapParaVender((b) => {
      b.sesion.secuencia_procesada = 1
      const cliente = b.clientes[0]
      if (cliente) cliente.saldo = '1000.50'
    })
    await aplicarBootstrap(nuevo)

    expect(await leerSaldoConsiderado(IDS_DE_PRUEBA.cliente)).toBe('1000.50')
  })

  it('una segunda cobranza rechazada no cuenta pero la primera, aceptada y pendiente de bootstrap, sí', async () => {
    await cobrar('a', '500.00')
    await cobrar('b', '100.00')
    await baseLocal.cola.where('operation_id').equals('op-cob-b').modify({ estado: 'RECHAZADO' })

    expect(await leerSaldoConsiderado(IDS_DE_PRUEBA.cliente)).toBe('1000.50')
  })

  it('el cobro de una venta rechazada sigue contando completo con su venta (CRE-08, ADR-065)', async () => {
    await sembrarVenta('v', { cajas: 1, unidades: 0, cobro: '20000.00' })
    await baseLocal.cola.where('operation_id').equals('op-v').modify({ estado: 'RECHAZADO' })

    // Débito 48.000 y cobro 20.000: saldo 1.500,50 + 28.000 = 29.500,50, con la venta rechazada.
    expect(await leerSaldoConsiderado(IDS_DE_PRUEBA.cliente)).toBe('29500.50')
  })
})
