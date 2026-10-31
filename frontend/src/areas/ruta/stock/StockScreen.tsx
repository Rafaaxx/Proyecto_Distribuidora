import { describirStock } from '../../../domain/ruta/lecturasLocales'
import { formatearFechaHora } from '../../../lib/fecha'
import { useStockLocal } from '../datos/lecturas'

/**
 * Stock de la ubicación tomada en `/ruta` (change 21, `design.md` D19; CAT-08, INV-04): por
 * producto, en cajas y unidades. Es el de la última descarga; sin costos.
 */
export function StockScreen() {
  const datos = useStockLocal()

  return (
    <div className="flex flex-col gap-3">
      <h1 className="text-lg font-semibold text-primary">Stock</h1>

      {datos.estado === 'cargando' && <p className="text-sm text-primary">Cargando…</p>}
      {datos.estado === 'sin_datos' && (
        <p className="text-sm text-primary">Todavía no hay datos descargados. Abrí una jornada desde el inicio.</p>
      )}
      {datos.estado === 'listo' && (
        <>
          <p className="text-xs text-primary/70">Datos de {formatearFechaHora(datos.fechaBootstrap).trim()}</p>
          {datos.filas.length === 0 ? (
            <p className="text-sm text-primary">No hay stock en tu ubicación.</p>
          ) : (
            <ul className="flex flex-col divide-y divide-border rounded-md border border-border bg-surface">
              {datos.filas.map((fila) => (
                <li key={fila.producto_id} className="flex items-center justify-between gap-2 px-3 py-3 text-sm text-primary">
                  <span className="font-medium">{fila.nombre}</span>
                  <span>{describirStock(fila.cajas, fila.unidades)}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

export default StockScreen
