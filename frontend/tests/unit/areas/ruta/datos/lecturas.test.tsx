import 'fake-indexeddb/auto'

import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import {
  useClientesLocales,
  useDatosDeInicio,
  useProductosLocales,
  useStockLocal,
} from '../../../../../src/areas/ruta/datos/lecturas'
import { baseLocal } from '../../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../../src/sync/aplicarBootstrap'
import { bootstrapDePrueba, clienteDePrueba } from '../../../utils/bootstrapDePrueba'

/**
 * Change 21, tarea 7.2 (spec `sync/base-local`, "Las pantallas de ruta leen siempre de la base
 * local"; RUT-03): hooks de lectura de Dexie que devuelven "sin datos" sin bootstrap.
 */
describe('hooks de lectura de la base local (change 21, tarea 7.2)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })

  it('sin bootstrap, todos devuelven "sin_datos"', async () => {
    const inicio = renderHook(() => useDatosDeInicio())
    const clientes = renderHook(() => useClientesLocales(''))
    const productos = renderHook(() => useProductosLocales('', new Date('2026-10-30T12:00:00Z')))
    const stock = renderHook(() => useStockLocal())

    await waitFor(() => {
      expect(inicio.result.current.estado).toBe('sin_datos')
      expect(clientes.result.current.estado).toBe('sin_datos')
      expect(productos.result.current.estado).toBe('sin_datos')
      expect(stock.result.current.estado).toBe('sin_datos')
    })
  })

  it('inicio: usuario, jornada, ubicación y hora de los datos', async () => {
    await aplicarBootstrap(bootstrapDePrueba())

    const { result } = renderHook(() => useDatosDeInicio())

    await waitFor(() => expect(result.current.estado).toBe('listo'))
    if (result.current.estado !== 'listo') throw new Error('esperaba datos')
    expect(result.current.usuario.usuario).toBe('vendedor')
    expect(result.current.jornada.ubicacion_nombre).toBe('Camioneta 1')
    expect(result.current.fechaBootstrap).toBe('2026-10-30T10:00:00Z')
  })

  it('clientes: ordenados con la cartera primero y filtrados por búsqueda', async () => {
    await aplicarBootstrap(
      bootstrapDePrueba({
        clientes: [
          { ...clienteDePrueba(3, 'Abasto Tres'), en_cartera: false },
          clienteDePrueba(2, 'Kiosco Dos'),
          clienteDePrueba(1, 'Almacén Uno'),
        ],
      }),
    )

    const todos = renderHook(() => useClientesLocales(''))
    const filtrados = renderHook(() => useClientesLocales('kiosco'))

    await waitFor(() => expect(todos.result.current.estado).toBe('listo'))
    await waitFor(() => expect(filtrados.result.current.estado).toBe('listo'))
    if (todos.result.current.estado !== 'listo' || filtrados.result.current.estado !== 'listo') {
      throw new Error('esperaba datos')
    }
    expect(todos.result.current.clientes.map((c) => c.nombre)).toEqual([
      'Almacén Uno',
      'Kiosco Dos',
      'Abasto Tres',
    ])
    expect(filtrados.result.current.clientes.map((c) => c.nombre)).toEqual(['Kiosco Dos'])
    expect(todos.result.current.fechaBootstrap).toBe('2026-10-30T10:00:00Z')
  })

  it('productos: precio por presentación de la versión vigente de la lista predeterminada, o null', async () => {
    await aplicarBootstrap(bootstrapDePrueba())

    const ahora = renderHook(() => useProductosLocales('', new Date('2026-10-30T12:00:00Z')))
    const antes = renderHook(() => useProductosLocales('', new Date('2026-09-01T00:00:00Z')))

    await waitFor(() => expect(ahora.result.current.estado).toBe('listo'))
    await waitFor(() => expect(antes.result.current.estado).toBe('listo'))
    if (ahora.result.current.estado !== 'listo' || antes.result.current.estado !== 'listo') {
      throw new Error('esperaba datos')
    }
    const producto = ahora.result.current.productos[0]
    expect(producto?.nombre).toBe('Gaseosa')
    expect(producto?.presentaciones.map((p) => [p.nombre, p.precio])).toEqual([
      ['Unidad', '8000.00'],
      ['Caja x6', '48000.00'],
    ])
    expect(antes.result.current.productos[0]?.presentaciones.map((p) => p.precio)).toEqual([null, null])
  })

  it('stock: cajas y unidades por producto', async () => {
    await aplicarBootstrap(bootstrapDePrueba())

    const { result } = renderHook(() => useStockLocal())

    await waitFor(() => expect(result.current.estado).toBe('listo'))
    if (result.current.estado !== 'listo') throw new Error('esperaba datos')
    expect(result.current.filas).toEqual([
      { producto_id: expect.any(String), nombre: 'Gaseosa', cantidad_base: 20, cajas: 3, unidades: 2 },
    ])
  })
})
