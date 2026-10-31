import 'fake-indexeddb/auto'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { baseLocal, TABLAS_MAESTRAS } from '../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../src/sync/aplicarBootstrap'
import {
  bootstrapDePrueba as bootstrap,
  clienteDePrueba as cliente,
  ID,
} from '../utils/bootstrapDePrueba'

/**
 * Change 21, tarea 6.1 (spec `sync/base-local`, "reemplaza los datos maestros en una sola
 * transacción"; ADR-006, INV-01, INV-03, INV-04, `02` §13.4).
 */
async function contar(): Promise<Record<string, number>> {
  const cuentas: Record<string, number> = {}
  for (const nombre of TABLAS_MAESTRAS) cuentas[nombre] = await baseLocal.table(nombre).count()
  return cuentas
}

describe('aplicar el bootstrap en una sola transacción (change 21, tarea 6.1)', () => {
  beforeEach(async () => {
    vi.restoreAllMocks()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })

  it('reemplaza por completo: el cliente que ya no viene desaparece', async () => {
    await aplicarBootstrap(bootstrap({ generado: '2026-10-29T10:00:00Z' }))
    expect(await baseLocal.clientes.count()).toBe(2)

    await aplicarBootstrap(
      bootstrap({ clientes: [cliente(1, 'Almacén Uno')], generado: '2026-10-30T10:00:00Z' }),
    )

    expect(await baseLocal.clientes.toArray()).toHaveLength(1)
    expect(await baseLocal.clientes.get(ID(102))).toBeUndefined()
    expect((await baseLocal.meta.get('fecha_bootstrap'))?.valor).toBe('2026-10-30T10:00:00Z')
    expect((await baseLocal.meta.get('jornada_id'))?.valor).toBe(ID(2))
  })

  it('adapta la respuesta a filas locales y deja los importes como string', async () => {
    await aplicarBootstrap(bootstrap())

    expect((await baseLocal.clientes.get(ID(101)))?.saldo).toBe('1500.50')
    expect(await baseLocal.presentaciones.where('producto_id').equals(ID(30)).count()).toBe(2)
    expect(await baseLocal.productos.get(ID(30))).not.toHaveProperty('presentaciones')
    expect(await baseLocal.precios.get([ID(51), ID(30)])).toEqual({
      version_id: ID(51),
      producto_id: ID(30),
      precio_referencia: '48000.00',
      unidades_referencia: 6,
    })
    expect((await baseLocal.versiones.get(ID(51)))?.lista_id).toBe(ID(50))
    expect((await baseLocal.stock.get(ID(30)))?.cantidad_base).toBe(20)
    expect((await baseLocal.sesion.get('actual'))?.usuario.usuario).toBe('vendedor')
    expect((await baseLocal.configuracion.get('organizacion'))?.intentos_pin_max).toBe(5)
    expect((await baseLocal.catalogos.get('alicuotas'))?.items).toHaveLength(1)
  })

  it('una falla a mitad del reemplazo deja completo el bootstrap anterior', async () => {
    await aplicarBootstrap(bootstrap({ generado: '2026-10-29T10:00:00Z' }))
    const antes = await contar()
    const clientesAntes = await baseLocal.clientes.toArray()

    vi.spyOn(baseLocal.productos, 'bulkPut').mockRejectedValue(new Error('falla inyectada'))

    await expect(
      aplicarBootstrap(bootstrap({ clientes: [cliente(9, 'Otro')], generado: '2026-10-30T10:00:00Z' })),
    ).rejects.toThrow('falla inyectada')

    vi.restoreAllMocks()
    expect(await contar()).toEqual(antes)
    expect(await baseLocal.clientes.toArray()).toEqual(clientesAntes)
    expect((await baseLocal.meta.get('fecha_bootstrap'))?.valor).toBe('2026-10-29T10:00:00Z')
  })

  it('el dispositivo_id queda intacto', async () => {
    await baseLocal.meta.put({ clave: 'dispositivo_id', valor: 'disp-1' })

    await aplicarBootstrap(bootstrap())
    await aplicarBootstrap(bootstrap())

    expect((await baseLocal.meta.get('dispositivo_id'))?.valor).toBe('disp-1')
  })

  it('doble aplicación: igual que la primera, sin duplicados', async () => {
    await aplicarBootstrap(bootstrap())
    const primera = await contar()
    const filas = await baseLocal.precios.toArray()

    await aplicarBootstrap(bootstrap())

    expect(await contar()).toEqual(primera)
    expect(await baseLocal.precios.toArray()).toEqual(filas)
  })

  it('solo toca las tablas de la lista explícita (ni meta ajena ni tablas de operaciones)', async () => {
    await baseLocal.meta.put({ clave: 'otra_cosa', valor: 'x' })

    await aplicarBootstrap(bootstrap())

    expect((await baseLocal.meta.get('otra_cosa'))?.valor).toBe('x')
    expect(TABLAS_MAESTRAS).not.toContain('meta')
    for (const operaciones of ['ventas', 'cobranzas', 'movimientos_locales', 'cola']) {
      expect(TABLAS_MAESTRAS).not.toContain(operaciones)
    }
  })

  describe('no toca las operaciones locales (change 22a, tarea 1.2; INV-01, SYN-09, 02 §13.4)', () => {
    async function sembrarOperaciones(): Promise<void> {
      await baseLocal.ventas.put({
        venta_id: 'v-1',
        operation_id: 'op-1',
        numero: 'V03-000142',
        cliente_id: ID(101),
        jornada_id: ID(2),
        occurred_at: '2026-10-30T10:30:00.000Z',
        estado_envio: 'PENDIENTE',
        contenido: {} as never,
        calculo: { lineas: [], total_neto: '31250.00', total_iva: '0.00', total: '31250.00' },
        nota: null,
      })
      await baseLocal.cobranzas.put({
        cobranza_id: 'c-1',
        venta_id: 'v-1',
        operation_id: 'op-1',
        jornada_id: ID(2),
        medios: [{ medio_pago_id: ID(20), importe: '20000.00', referencia: null }],
        total: '20000.00',
      })
      await baseLocal.movimientos_locales.bulkAdd([
        { operation_id: 'op-1', jornada_id: ID(2), tipo: 'VENTA_STOCK', producto_id: ID(30), cliente_id: null, cantidad_base: -15, importe: null, estado_operacion: 'PENDIENTE' },
        { operation_id: 'op-1', jornada_id: ID(2), tipo: 'VENTA_DEBITO', producto_id: null, cliente_id: ID(101), cantidad_base: null, importe: '31250.00', estado_operacion: 'PENDIENTE' },
      ])
      await baseLocal.cola.put({
        secuencia: 7,
        operation_id: 'op-1',
        estado: 'PENDIENTE',
        sobre: { operation_id: 'op-1' } as never,
      })
      await baseLocal.intentos_pin.put({
        usuario_id: ID(1),
        autorizador_id: ID(5),
        fallos: 2,
        derivacion: 'der-1',
        bloqueado: false,
      })
      await baseLocal.meta.bulkPut([
        { clave: 'ultimo_correlativo', valor: '142' },
        { clave: 'ultima_secuencia', valor: '7' },
      ])
    }

    async function instantanea(): Promise<unknown> {
      return {
        ventas: await baseLocal.ventas.toArray(),
        cobranzas: await baseLocal.cobranzas.toArray(),
        movimientos: await baseLocal.movimientos_locales.toArray(),
        cola: await baseLocal.cola.toArray(),
        intentos: await baseLocal.intentos_pin.toArray(),
        correlativo: (await baseLocal.meta.get('ultimo_correlativo'))?.valor,
        secuencia: (await baseLocal.meta.get('ultima_secuencia'))?.valor,
      }
    }

    it('aplicar un bootstrap deja idénticas ventas, cobranzas, movimientos, cola y contadores, y reinicia los intentos de PIN (D10 = B; ADR-055)', async () => {
      await sembrarOperaciones()
      const antes = { ...(await instantanea()), intentos: [] }

      await aplicarBootstrap(bootstrap({ generado: '2026-10-30T11:00:00Z' }))
      await aplicarBootstrap(bootstrap({ clientes: [cliente(1, 'Otro')], generado: '2026-10-30T12:00:00Z' }))

      expect(await instantanea()).toEqual(antes)
      expect(await baseLocal.intentos_pin.count()).toBe(0)
      expect(await baseLocal.ventas.count()).toBe(1)
      expect(await baseLocal.movimientos_locales.count()).toBe(2)
    })

    it('un bootstrap que falla a mitad deja las operaciones y los maestros anteriores', async () => {
      await aplicarBootstrap(bootstrap({ generado: '2026-10-29T10:00:00Z' }))
      await sembrarOperaciones()
      const antes = await instantanea()
      const clientesAntes = await baseLocal.clientes.toArray()

      vi.spyOn(baseLocal.productos, 'bulkPut').mockRejectedValue(new Error('falla inyectada'))
      await expect(
        aplicarBootstrap(bootstrap({ clientes: [cliente(9, 'Otro')], generado: '2026-10-30T10:00:00Z' })),
      ).rejects.toThrow('falla inyectada')
      vi.restoreAllMocks()

      expect(await instantanea()).toEqual(antes)
      expect(await baseLocal.clientes.toArray()).toEqual(clientesAntes)
    })
  })
})
