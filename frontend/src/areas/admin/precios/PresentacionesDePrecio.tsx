import { precioPorPresentacion } from '../../../domain/precios/presentacion'
import { formatearImporte, parsearImporteDesdeApi } from '../../../lib/money'

interface PresentacionDeVenta {
  nombre: string
  unidades_base: number
}

/**
 * Precio de cada presentación de venta de un producto, calculado con PRC-22 a partir del precio
 * de referencia y de las unidades de referencia guardadas en el precio (D1, D10). Las
 * presentaciones (activas y de venta, de menos unidades a más) vienen en la línea del precio:
 * no se pide el detalle de cada producto al catálogo. Es solo para mostrar: nunca se usa para
 * armar totales (`$1.433,33 x 3` no es el bruto de 3 unidades).
 */
export function PresentacionesDePrecio({
  precioReferencia,
  unidadesReferencia,
  presentaciones,
}: {
  precioReferencia: string
  unidadesReferencia: number
  presentaciones: readonly PresentacionDeVenta[]
}) {
  if (presentaciones.length === 0) return null
  return (
    <ul className="flex flex-col text-xs text-primary/70">
      {presentaciones.map((presentacion) => (
        <li key={presentacion.nombre}>
          {presentacion.nombre} ({presentacion.unidades_base} u.): ${' '}
          {formatearImporte(
            parsearImporteDesdeApi(precioPorPresentacion(precioReferencia, unidadesReferencia, presentacion.unidades_base)),
          )}
        </li>
      ))}
    </ul>
  )
}
