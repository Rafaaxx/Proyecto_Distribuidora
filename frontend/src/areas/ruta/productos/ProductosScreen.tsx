import { useState } from 'react'

import { describirStock, formatearDinero } from '../../../domain/ruta/lecturasLocales'
import { formatearFechaHora } from '../../../lib/fecha'
import { useProductosLocales, useStockLocal } from '../datos/lecturas'
import { useAhora } from '../datos/useAhora'

/**
 * Productos de `/ruta` (change 21, `design.md` D6, D19; PRC-20, PRC-22, CAT-08, INV-03, INV-04).
 * Precio por presentación de la versión vigente AHORA de la lista predeterminada (o "Sin precio")
 * y stock de la ubicación en cajas y unidades. Nunca muestra costos: el bootstrap no los trae.
 */
export function ProductosScreen() {
  const [busqueda, setBusqueda] = useState('')
  const ahora = useAhora()
  const datos = useProductosLocales(busqueda, ahora)
  const stock = useStockLocal()
  const stockPorProducto = new Map(
    stock.estado === 'listo' ? stock.filas.map((fila) => [fila.producto_id, fila]) : [],
  )

  return (
    <div className="flex flex-col gap-3">
      <h1 className="text-lg font-semibold text-primary">Productos</h1>

      {datos.estado === 'cargando' && <p className="text-sm text-primary">Cargando…</p>}
      {datos.estado === 'sin_datos' && (
        <p className="text-sm text-primary">Todavía no hay datos descargados. Abrí una jornada desde el inicio.</p>
      )}
      {datos.estado === 'listo' && (
        <>
          <p className="text-xs text-primary/70">Datos de {formatearFechaHora(datos.fechaBootstrap).trim()}</p>
          <div className="flex flex-col gap-1">
            <label htmlFor="buscar-producto" className="text-sm font-medium text-primary">
              Buscar producto
            </label>
            <input
              id="buscar-producto"
              type="search"
              className="rounded-md border border-border px-2 py-2 text-sm"
              placeholder="Nombre o código"
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
            />
          </div>
          {datos.productos.length === 0 ? (
            <p className="text-sm text-primary">No hay productos que coincidan con la búsqueda.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {datos.productos.map((producto) => {
                const fila = stockPorProducto.get(producto.id)
                return (
                  <li key={producto.id} className="rounded-md border border-border bg-surface p-3">
                    <p className="text-sm font-semibold text-primary">{producto.nombre}</p>
                    <p className="text-xs text-primary/70">{producto.codigo}</p>
                    <ul className="mt-2 flex flex-col gap-1">
                      {producto.presentaciones.map((presentacion) => (
                        <li key={presentacion.id} className="flex justify-between gap-2 text-sm text-primary">
                          <span>{presentacion.nombre}</span>
                          <span>{presentacion.precio === null ? 'Sin precio' : formatearDinero(presentacion.precio)}</span>
                        </li>
                      ))}
                    </ul>
                    <p className="mt-2 text-sm text-primary">
                      {describirStock(fila?.cajas ?? 0, fila?.unidades ?? 0)}
                    </p>
                  </li>
                )
              })}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

export default ProductosScreen
