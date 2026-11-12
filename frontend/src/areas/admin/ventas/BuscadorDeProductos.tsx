import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { formatearMonto } from '../../../domain/cuentas-corrientes/presentacion'
import { formatearCantidad, referenciaDePresentaciones } from '../../../domain/stock/cantidades'
import type { ProductoParaVender } from '../../../features/ventas/api'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

export interface BuscadorDeProductosProps {
  texto: string
  alCambiarTexto: (texto: string) => void
  resultados: readonly ProductoParaVender[]
  cargando: boolean
  hayMas: boolean
  cargandoMas: boolean
  alCargarMas: () => void
  /** Productos que ya están en el pedido. */
  agregados: ReadonlySet<string>
  alAgregar: (producto: ProductoParaVender) => void
  /** Hay un cliente elegido: sin él no hay lista aplicable y no se busca (PRC-20). */
  hayCliente: boolean
}

/**
 * Buscador de productos de "Nueva venta" (change 18a, D19, D21): la búsqueda y la paginación las
 * hace el servidor; cada resultado trae el precio de la versión y el stock de la ubicación. Un
 * producto sin precio se muestra pero no se puede agregar (VTA-10, D7). Sin lógica de negocio.
 */
export function BuscadorDeProductos({
  texto,
  alCambiarTexto,
  resultados,
  cargando,
  hayMas,
  cargandoMas,
  alCargarMas,
  agregados,
  alAgregar,
  hayCliente,
}: BuscadorDeProductosProps) {
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="text-base font-semibold text-primary">Productos</h2>
      <Campo id="venta-buscar-producto" etiqueta="Buscar producto">
        <input
          id="venta-buscar-producto"
          className={CLASE_CONTROL}
          placeholder="Nombre o código"
          value={texto}
          onChange={(evento) => alCambiarTexto(evento.target.value)}
          disabled={!hayCliente}
        />
      </Campo>
      <div className="flex flex-wrap items-center gap-3 text-sm text-primary/70">
        <span className="flex items-center gap-1">
          Precio <Ayuda clave="ventas.precio" />
        </span>
        <span className="flex items-center gap-1">
          Stock <Ayuda clave="ventas.stock" />
        </span>
      </div>
      {!hayCliente && <p className="text-sm text-primary/70">Elegí un cliente para ver los precios de su lista.</p>}
      {hayCliente && cargando && <p className="text-sm text-primary/70">Buscando…</p>}
      {hayCliente && !cargando && resultados.length === 0 && (
        <p className="text-sm text-primary/70">No hay productos que coincidan.</p>
      )}
      <ul className="flex flex-col gap-2">
        {resultados.map((producto) => {
          const referencia = referenciaDePresentaciones(producto.presentaciones)
          const yaAgregado = agregados.has(producto.producto_id)
          return (
            <li
              key={producto.producto_id}
              data-testid={`resultado-${producto.producto_id}`}
              className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-sm text-primary"
            >
              <div className="flex flex-col">
                <span className="font-medium">
                  {producto.nombre} <span className="text-primary/60">({producto.codigo})</span>
                </span>
                {producto.sin_precio || producto.precio_referencia === null ? (
                  <span className="text-danger">Sin precio en la lista</span>
                ) : (
                  <span>
                    Precio {formatearMonto(producto.precio_referencia)} por{' '}
                    {String(producto.unidades_referencia ?? 1)} {producto.unidades_referencia === 1 ? 'unidad' : 'unidades'}
                  </span>
                )}
                {producto.stock_base !== null && <span>Stock: {formatearCantidad(producto.stock_base, referencia)}</span>}
              </div>
              <Boton
                variante="secundario"
                aria-label={`Agregar ${producto.nombre}`}
                disabled={producto.sin_precio || yaAgregado}
                onClick={() => alAgregar(producto)}
              >
                {yaAgregado ? 'Agregado' : 'Agregar'}
              </Boton>
            </li>
          )
        })}
      </ul>
      {hayMas && (
        <div>
          <Boton variante="secundario" disabled={cargandoMas} onClick={alCargarMas}>
            Cargar más productos
          </Boton>
        </div>
      )}
    </Card>
  )
}
