import 'fake-indexeddb/auto'

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { bootstrapDePrueba, ID } from '../../utils/bootstrapDePrueba'
import { montarEnRuta } from '../../utils/rutaDePrueba'

import { ProductosScreen } from '../../../../src/areas/ruta/productos/ProductosScreen'
import { StockScreen } from '../../../../src/areas/ruta/stock/StockScreen'
import { describirStock } from '../../../../src/domain/ruta/lecturasLocales'
import { baseLocal } from '../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../src/sync/aplicarBootstrap'

/**
 * Change 21, tarea 14.2 (spec `ruta/area-de-ruta`, "Productos y stock desde la base local"; cita
 * PRC-20, PRC-22, CAT-08, INV-04, INV-03): búsqueda, precio por presentación de la versión vigente
 * AHORA de la lista predeterminada o "Sin precio", versión programada tomada a su hora (reloj
 * falso), stock en cajas y unidades, ningún costo.
 */
function producto(n: number, nombre: string, codigo: string) {
  return {
    id: ID(300 + n),
    codigo,
    nombre,
    categoria_id: ID(40),
    marca_id: null,
    alicuota_id: ID(22),
    alicuota_valor: '0.210000',
    presentacion_referencia_id: ID(310 + n),
    presentaciones: [
      { id: ID(310 + n), nombre: 'Caja x6', unidades_base: 6, es_referencia: true },
      { id: ID(320 + n), nombre: 'Unidad', unidades_base: 1, es_referencia: false },
    ],
  }
}

async function sembrar(opciones: { programada?: boolean; stock?: [number, number][] } = {}) {
  const b = bootstrapDePrueba()
  b.productos = [producto(1, 'Malbec 750', 'MAL'), producto(2, 'Agua 500', 'AGU'), producto(3, 'Sin Precio Cola', 'SPC')]
  const version = b.listas[0]?.versiones[0]
  if (version === undefined) throw new Error('el bootstrap de prueba trae una versión')
  version.precios = [
    { producto_id: ID(301), precio_referencia: '48000.00', unidades_referencia: 6 },
    { producto_id: ID(302), precio_referencia: '9000.00', unidades_referencia: 6 },
  ]
  if (opciones.programada) {
    b.listas[0]?.versiones.push({
      id: ID(52),
      numero: 2,
      estado: 'PROGRAMADA',
      vigencia_desde: '2026-10-30T17:00:00Z',
      vigencia_hasta: null,
      precios: [{ producto_id: ID(301), precio_referencia: '54000.00', unidades_referencia: 6 }],
    })
  }
  b.stock = (opciones.stock ?? [[301, 20]]).map(([producto_id, cantidad_base]) => ({
    producto_id: ID(producto_id),
    cantidad_base,
  }))
  await aplicarBootstrap(b)
}

describe('describirStock (INV-04, CAT-08)', () => {
  it.each([
    [3, 2, '3 cajas y 2 unidades'],
    [1, 1, '1 caja y 1 unidad'],
    [4, 0, '4 cajas'],
    [0, 5, '5 unidades'],
    [0, 0, 'Sin stock'],
  ])('%i cajas, %i unidades -> %s', (cajas, unidades, esperado) => {
    expect(describirStock(cajas, unidades)).toBe(esperado)
  })
})

describe('ProductosScreen (tarea 14.2)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('muestra el precio por presentación de la versión vigente y el stock en cajas y unidades', async () => {
    await sembrar()
    montarEnRuta(<ProductosScreen />)

    const malbec = (await screen.findByText('Malbec 750')).closest('li') as HTMLElement
    expect(within(malbec).getByText('$ 48.000,00')).toBeInTheDocument() // caja de 6
    expect(within(malbec).getByText('$ 8.000,00')).toBeInTheDocument() // unidad
    expect(within(malbec).getByText('3 cajas y 2 unidades')).toBeInTheDocument()
    const agua = screen.getByText('Agua 500').closest('li') as HTMLElement
    expect(within(agua).getByText('$ 9.000,00')).toBeInTheDocument()
    expect(within(agua).getByText('$ 1.500,00')).toBeInTheDocument()
    expect(within(agua).getByText('Sin stock')).toBeInTheDocument()
  })

  it('un producto sin precio en la versión vigente muestra "Sin precio"', async () => {
    await sembrar()
    montarEnRuta(<ProductosScreen />)

    const sinPrecio = (await screen.findByText('Sin Precio Cola')).closest('li') as HTMLElement
    expect(within(sinPrecio).getAllByText('Sin precio')).toHaveLength(2)
  })

  it('busca por nombre o por código', async () => {
    await sembrar()
    montarEnRuta(<ProductosScreen />)
    const u = userEvent.setup()

    await u.type(await screen.findByLabelText('Buscar producto'), 'agu')
    await waitFor(() => expect(screen.queryByText('Malbec 750')).not.toBeInTheDocument())
    expect(screen.getByText('Agua 500')).toBeInTheDocument()

    await u.clear(screen.getByLabelText('Buscar producto'))
    await u.type(screen.getByLabelText('Buscar producto'), 'mal')
    expect(await screen.findByText('Malbec 750')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText('Agua 500')).not.toBeInTheDocument())
  })

  it('la versión programada se toma a su hora: antes de las 17:00 UTC rige la 1, después la 2 (PRC-20)', async () => {
    await sembrar({ programada: true })
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-30T16:55:00Z'))
    const antes = montarEnRuta(<ProductosScreen />)
    expect(await screen.findByText('$ 48.000,00')).toBeInTheDocument()
    antes.unmount()

    vi.setSystemTime(new Date('2026-10-30T17:05:00Z'))
    montarEnRuta(<ProductosScreen />)
    expect(await screen.findByText('$ 54.000,00')).toBeInTheDocument()
    expect(screen.queryByText('$ 48.000,00')).not.toBeInTheDocument()
  })

  it('no muestra ningún costo ni margen', async () => {
    await sembrar()
    montarEnRuta(<ProductosScreen />)
    await screen.findByText('Malbec 750')
    expect(document.body.textContent).not.toMatch(/costo|margen|utilidad/i)
  })

  it('sin bootstrap avisa que no hay datos descargados', async () => {
    montarEnRuta(<ProductosScreen />)
    expect(await screen.findByText(/todavía no hay datos descargados/i)).toBeInTheDocument()
  })
})

describe('StockScreen (tarea 14.2)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })

  it('lista el stock de la ubicación por producto en cajas y unidades, ordenado por nombre', async () => {
    await sembrar({ stock: [[301, 20], [302, 12], [303, 4]] })
    montarEnRuta(<StockScreen />)

    await screen.findByText('Malbec 750')
    const filas = within(screen.getByRole('list')).getAllByRole('listitem')
    expect(filas.map((f) => f.textContent)).toEqual([
      'Agua 5002 cajas',
      'Malbec 7503 cajas y 2 unidades',
      'Sin Precio Cola4 unidades',
    ])
  })

  it('sin stock cargado lo dice, y nunca muestra costos', async () => {
    await sembrar({ stock: [] })
    montarEnRuta(<StockScreen />)
    expect(await screen.findByText(/no hay stock en tu ubicación/i)).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/costo|margen/i)
  })
})
