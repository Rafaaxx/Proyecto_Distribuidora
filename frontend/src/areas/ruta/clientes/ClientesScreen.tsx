import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Ayuda } from '../../../components/ui/Ayuda'
import { Badge } from '../../../components/ui/Badge'
import { formatearFechaHora } from '../../../lib/fecha'
import { useClientesLocales } from '../datos/lecturas'

/**
 * Clientes de `/ruta` (change 21, `design.md` D19; `01` §19, CLI-02, INV-17). Lee solo de la base
 * local: primero el consumidor final y la cartera, después el resto; la búsqueda recorre a todos.
 */
export function ClientesScreen() {
  const [busqueda, setBusqueda] = useState('')
  const datos = useClientesLocales(busqueda)

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-1">
        <h1 className="text-lg font-semibold text-primary">Clientes</h1>
        <Ayuda clave="ruta.cartera" />
      </div>

      {datos.estado === 'cargando' && <p className="text-sm text-primary">Cargando…</p>}
      {datos.estado === 'sin_datos' && (
        <p className="text-sm text-primary">Todavía no hay datos descargados. Abrí una jornada desde el inicio.</p>
      )}
      {datos.estado === 'listo' && (
        <>
          <p className="text-xs text-primary/70">Datos de {formatearFechaHora(datos.fechaBootstrap).trim()}</p>
          <div className="flex flex-col gap-1">
            <label htmlFor="buscar-cliente" className="text-sm font-medium text-primary">
              Buscar cliente
            </label>
            <input
              id="buscar-cliente"
              type="search"
              className="rounded-md border border-border px-2 py-2 text-sm"
              placeholder="Nombre, código o documento"
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
            />
          </div>
          {datos.clientes.length === 0 ? (
            <p className="text-sm text-primary">No hay clientes que coincidan con la búsqueda.</p>
          ) : (
            <ul className="flex flex-col divide-y divide-border rounded-md border border-border bg-surface">
              {datos.clientes.map((cliente) => (
                <li key={cliente.id} className="flex items-center justify-between gap-2 px-3 py-3">
                  <Link to={`/ruta/clientes/${cliente.id}`} className="text-sm font-medium text-primary underline">
                    <span>{cliente.nombre}</span>
                    {cliente.codigo && <span className="font-normal text-primary/70"> · {cliente.codigo}</span>}
                  </Link>
                  <span className="flex gap-1">
                    {cliente.es_consumidor_final && <Badge>Consumidor final</Badge>}
                    {cliente.estado === 'SUSPENDIDO' && <Badge variante="negativo">Suspendido</Badge>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

export default ClientesScreen
