import { Ayuda } from '../../../components/ui/Ayuda'
import { Badge } from '../../../components/ui/Badge'
import type { ClienteParaElegir } from '../../../domain/ruta/carritoDeRuta'
import { formatearDinero } from '../../../domain/ruta/lecturasLocales'

/**
 * Paso 1 de la venta de ruta: elegir el cliente (change 22a, `design.md` D14; CLI-02, CRE-01,
 * CRE-08). Cartera primero y búsqueda en todos; muestra estado, saldo y crédito local. Sin lógica
 * de negocio: la lista llega armada de `domain/ruta/carritoDeRuta.ts`.
 */
export interface PasoClienteProps {
  clientes: readonly ClienteParaElegir[]
  busqueda: string
  alBuscar: (texto: string) => void
  alElegir: (clienteId: string) => void
}

export function PasoCliente({ clientes, busqueda, alBuscar, alElegir }: PasoClienteProps) {
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-1">
          <label htmlFor="vender-buscar-cliente" className="text-sm font-medium text-primary">
            Buscar cliente
          </label>
          <Ayuda clave="ruta.cartera" />
        </div>
        <input
          id="vender-buscar-cliente"
          type="search"
          className="w-full rounded-md border border-border px-2 py-2 text-sm"
          placeholder="Nombre, código o documento"
          value={busqueda}
          onChange={(evento) => alBuscar(evento.target.value)}
        />
      </div>
      {clientes.length === 0 ? (
        <p className="text-sm text-primary">No hay clientes que coincidan con la búsqueda.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {clientes.map(({ cliente, saldoConsiderado, disponible }) => (
            <li key={cliente.id}>
              <button
                type="button"
                onClick={() => alElegir(cliente.id)}
                className="flex w-full min-w-0 flex-col gap-1 rounded-md border border-border bg-surface p-3 text-left hover:bg-surface-muted"
              >
                <span className="flex flex-wrap items-center gap-2">
                  <span className="break-words text-sm font-semibold text-primary">{cliente.nombre}</span>
                  {cliente.es_consumidor_final && <Badge>Consumidor final</Badge>}
                  {cliente.estado === 'SUSPENDIDO' && <Badge variante="negativo">Suspendido</Badge>}
                </span>
                {saldoConsiderado !== null && (
                  <span className="text-xs text-primary/70">
                    Saldo {formatearDinero(saldoConsiderado)}
                    {cliente.credito.limite === null
                      ? ' · Sin límite'
                      : ` · Disponible ${formatearDinero(disponible ?? '0.00')}`}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
