import 'fake-indexeddb/auto'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { calcularVenta, type LineaCalculo } from '../../../src/domain/calculo'
import { baseLocal, type ContenidoDeVentaLocal } from '../../../src/lib/dispositivo/db'
import { definirPin, desbloquearConPin } from '../../../src/lib/sesionLocal/pin'
import { borrarSesionLocal } from '../../../src/lib/sesionLocal/sesionLocal'
import { aplicarBootstrap } from '../../../src/sync/aplicarBootstrap'
import { confirmarVentaLocal, type EntradaDeConfirmacion } from '../../../src/sync/confirmarVentaLocal'
import { bootstrapDePrueba, ID } from '../utils/bootstrapDePrueba'

/**
 * Change 22a, tareas 4.1 y 4.2 (spec `sync/cola-local`, "Confirmar una venta local es una sola
 * transacción" y "Las operaciones locales no se borran hasta su resultado"; `design.md` D4, D13;
 * INV-01, INV-06, INV-03, INV-04, SYN-09, SEG-04). El bootstrap de prueba trae el prefijo
 * `0001` y el último correlativo 7.
 */
function lineaDeCalculo(id: string, cantidadBase: number): LineaCalculo {
  return {
    id,
    precioReferencia: '12500.00',
    unidadesReferencia: 6,
    cantidadBase,
    alicuota: '0.210000',
    productoId: ID(30),
    categoriaId: 'cat',
    marcaId: 'marca',
    descuentoManual: null,
  }
}

function entrada(
  sufijo: string,
  opciones: { cobrar?: boolean; operationId?: string } = {},
): EntradaDeConfirmacion {
  const calculo = calcularVenta(
    'A',
    [lineaDeCalculo(`l-${sufijo}-1`, 12), lineaDeCalculo(`l-${sufijo}-2`, 3)],
    [],
    null,
  )
  const cobrar = opciones.cobrar ?? true
  const contenido = {
    venta_id: `venta-${sufijo}`,
    numero: 'se-reasigna-al-confirmar',
    cliente_id: ID(101),
    ubicacion_id: null,
    lista_id: null,
    lista_version_id: null,
    motivo_lista_id: null,
    lineas: [],
    total: calculo.total.toFixed(2),
    cobranza: cobrar
      ? {
          cobranza_id: `cobranza-${sufijo}`,
          medios: [{ medio_pago_id: ID(20), importe: '20000.00', referencia: null }],
          observacion: null,
        }
      : null,
    credito: {
      limite: '100000.00',
      saldo_considerado: '1500.50',
      politica: 'AUTORIZAR',
      resolucion: 'SIN_EXCESO',
    },
  } as unknown as ContenidoDeVentaLocal
  return {
    contenido,
    calculo,
    lineas: [
      { lineaId: `l-${sufijo}-1`, productoId: ID(30), cantidadBase: 12 },
      { lineaId: `l-${sufijo}-2`, productoId: ID(30), cantidadBase: 3 },
    ],
    operationId: opciones.operationId ?? `op-${sufijo}`,
    usuarioId: ID(1),
    dispositivoId: 'disp-1',
    ahora: new Date('2026-10-30T10:30:00.000Z'),
    appVersion: '1.0.0',
    nota: null,
  }
}

async function contar(): Promise<Record<string, number>> {
  return {
    ventas: await baseLocal.ventas.count(),
    cobranzas: await baseLocal.cobranzas.count(),
    movimientos: await baseLocal.movimientos_locales.count(),
    cola: await baseLocal.cola.count(),
  }
}

async function contadores(): Promise<[string | undefined, string | undefined]> {
  return [
    (await baseLocal.meta.get('ultimo_correlativo'))?.valor,
    (await baseLocal.meta.get('ultima_secuencia'))?.valor,
  ]
}

describe('confirmar una venta local en una sola transacción (change 22a, tarea 4.1)', () => {
  beforeEach(async () => {
    vi.restoreAllMocks()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapDePrueba())
  })

  it('escribe venta, cobranza, movimientos, comando y contadores con el mismo operation_id (INV-01, VTA-12, RUT-04)', async () => {
    const resultado = await confirmarVentaLocal(entrada('a'))

    expect(resultado.repetida).toBe(false)
    expect(resultado.venta.numero).toBe('0001-000008')
    expect(await contar()).toEqual({ ventas: 1, cobranzas: 1, movimientos: 4, cola: 1 })
    const venta = await baseLocal.ventas.get('venta-a')
    expect(venta).toMatchObject({
      operation_id: 'op-a',
      numero: '0001-000008',
      estado_envio: 'PENDIENTE',
      jornada_id: ID(2),
    })
    expect(venta?.calculo.total).toBe('31250.00')
    expect((await baseLocal.cobranzas.get('cobranza-a'))?.total).toBe('20000.00')
    const movimientos = await baseLocal.movimientos_locales.toArray()
    expect(movimientos.every((m) => m.operation_id === 'op-a')).toBe(true)
    expect(movimientos.filter((m) => m.tipo === 'VENTA_STOCK').map((m) => m.cantidad_base)).toEqual([-12, -3])
    expect(movimientos.find((m) => m.tipo === 'VENTA_DEBITO')?.importe).toBe('31250.00')
    expect(movimientos.find((m) => m.tipo === 'COBRANZA_CREDITO')?.importe).toBe('20000.00')
    const [comando] = await baseLocal.cola.toArray()
    expect(comando).toMatchObject({ operation_id: 'op-a', estado: 'PENDIENTE', secuencia: 1 })
    expect(comando?.sobre).toMatchObject({
      tipo: 'VENTA_CONFIRMAR',
      modo: 'OFFLINE',
      jornada_id: ID(2),
      usuario_id: ID(1),
      dispositivo_id: 'disp-1',
      secuencia: 1,
      occurred_at: '2026-10-30T10:30:00.000Z',
    })
    expect(comando?.sobre.contenido.numero).toBe('0001-000008')
    expect(await contadores()).toEqual(['8', '1'])
  })

  it('dos ventas seguidas: número y secuencia crecen sin huecos ni repeticiones (VTA-06, SYN-03)', async () => {
    await confirmarVentaLocal(entrada('a'))
    const segunda = await confirmarVentaLocal(entrada('b', { cobrar: false }))

    expect(segunda.venta.numero).toBe('0001-000009')
    const cola = await baseLocal.cola.orderBy('secuencia').toArray()
    expect(cola.map((c) => [c.secuencia, c.operation_id])).toEqual([
      [1, 'op-a'],
      [2, 'op-b'],
    ])
    expect(await contadores()).toEqual(['9', '2'])
    expect(await baseLocal.cobranzas.count()).toBe(1)
  })

  it('una falla al escribir la cola no deja nada y los contadores no avanzan (INV-01)', async () => {
    vi.spyOn(baseLocal.cola, 'add').mockRejectedValue(new Error('falla inyectada'))

    await expect(confirmarVentaLocal(entrada('a'))).rejects.toThrow('falla inyectada')
    vi.restoreAllMocks()

    expect(await contar()).toEqual({ ventas: 0, cobranzas: 0, movimientos: 0, cola: 0 })
    expect(await contadores()).toEqual([undefined, undefined])

    // El carrito sigue abierto: reintentar confirma con el mismo número, sin hueco.
    const reintento = await confirmarVentaLocal(entrada('a'))
    expect(reintento.venta.numero).toBe('0001-000008')
    expect(await contar()).toEqual({ ventas: 1, cobranzas: 1, movimientos: 4, cola: 1 })
  })

  it('una falla tardía (al actualizar los contadores) también revierte todo (INV-01)', async () => {
    await confirmarVentaLocal(entrada('a'))
    const antes = await contar()
    vi.spyOn(baseLocal.meta, 'bulkPut').mockRejectedValue(new Error('falla en contadores'))

    await expect(confirmarVentaLocal(entrada('b'))).rejects.toThrow('falla en contadores')
    vi.restoreAllMocks()

    expect(await contar()).toEqual(antes)
    expect(await contadores()).toEqual(['8', '1'])
  })

  it('reconfirmar con el mismo operation_id no crea otra venta ni otro comando (INV-06, SYN-02)', async () => {
    const primera = await confirmarVentaLocal(entrada('a'))
    const repetida = await confirmarVentaLocal(entrada('a'))
    const triple = await confirmarVentaLocal(entrada('a'))

    expect(repetida.repetida).toBe(true)
    expect(triple.repetida).toBe(true)
    expect(repetida.venta.numero).toBe(primera.venta.numero)
    expect(await contar()).toEqual({ ventas: 1, cobranzas: 1, movimientos: 4, cola: 1 })
    expect(await contadores()).toEqual(['8', '1'])
  })

  it('importes con dos decimales y cantidades enteras en todo lo guardado (INV-03, INV-04)', async () => {
    await confirmarVentaLocal(entrada('a'))

    const venta = await baseLocal.ventas.get('venta-a')
    for (const l of venta?.calculo.lineas ?? []) {
      for (const importe of [l.bruto, l.neto, l.descuento_total, l.importe_iva]) {
        expect(importe).toMatch(/^\d+\.\d{2}$/)
      }
    }
    for (const m of await baseLocal.movimientos_locales.toArray()) {
      if (m.importe !== null) expect(m.importe).toMatch(/^\d+\.\d{2}$/)
      if (m.cantidad_base !== null) expect(Number.isInteger(m.cantidad_base)).toBe(true)
    }
    for (const medio of (await baseLocal.cobranzas.get('cobranza-a'))?.medios ?? []) {
      expect(medio.importe).toMatch(/^\d+\.\d{2}$/)
    }
  })

  it('sin sesión local no hay con qué numerar: falla y no escribe nada', async () => {
    await baseLocal.sesion.clear()

    await expect(confirmarVentaLocal(entrada('a'))).rejects.toThrow(/sesión/)
    expect(await contar()).toEqual({ ventas: 0, cobranzas: 0, movimientos: 0, cola: 0 })
  })
})

describe('las operaciones locales no se borran hasta su resultado (change 22a, tarea 4.2)', () => {
  beforeEach(async () => {
    vi.restoreAllMocks()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapDePrueba())
  })

  it('la venta nace "Sin enviar" (PENDIENTE) (SYN-09)', async () => {
    const { venta } = await confirmarVentaLocal(entrada('a'))

    expect(venta.estado_envio).toBe('PENDIENTE')
    expect((await baseLocal.cola.toArray())[0]?.estado).toBe('PENDIENTE')
  })

  it('borrar la sesión local (cerrar sesión) no toca ventas, cobranzas, movimientos, cola ni contadores (SYN-09, SEG-04)', async () => {
    await confirmarVentaLocal(entrada('a'))
    const antes = { cuentas: await contar(), contadores: await contadores() }
    const filas = await baseLocal.cola.toArray()

    await borrarSesionLocal()

    expect(await contar()).toEqual(antes.cuentas)
    expect(await contadores()).toEqual(antes.contadores)
    expect(await baseLocal.cola.toArray()).toEqual(filas)
    expect(await baseLocal.clientes.count()).toBe(0)
  })

  it('el bloqueo del PIN de desbloqueo no toca las tablas de operaciones (SEG-04)', async () => {
    await definirPin('482915', '482915')
    await confirmarVentaLocal(entrada('a'))
    const antes = await contar()
    // Un fallo más para llegar al máximo de 10 sin derivar el PIN diez veces.
    await baseLocal.meta.put({ clave: 'pin_intentos', valor: '9' })

    expect(await desbloquearConPin('000000')).toEqual({ tipo: 'bloqueado' })

    expect(await contar()).toEqual(antes)
    expect(await baseLocal.cola.count()).toBe(1)
    expect((await baseLocal.ventas.get('venta-a'))?.estado_envio).toBe('PENDIENTE')
  }, 20_000)
})
