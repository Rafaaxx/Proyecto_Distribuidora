import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { formatearMonto } from '../../../domain/cuentas-corrientes/presentacion'
import type { LineaVisible } from '../../../domain/ventas/pedido'
import { textoDeCantidadDeLinea } from '../../../domain/ventas/presentacion'

const CLASE_CANTIDAD = 'w-24 rounded-md border border-border px-2 py-1 text-sm'

export interface ItemDeVentaProps {
  productoId: string
  nombre: string
  cajas: number
  unidades: number
  admiteCajas: boolean
  admiteUnidadesSueltas: boolean
  lineas: readonly LineaVisible[]
  /** Mensaje del producto que no se puede vender como está pedido (sin precio, cantidad inválida). */
  error?: string
  /** Texto de aviso cuando lo pedido supera el stock de la ubicación. */
  avisoDeStock?: string
  /** Texto cuando el precio de este producto todavía no llegó o no se pudo leer. */
  estado?: string
  alCambiarCajas: (cajas: number) => void
  alCambiarUnidades: (unidades: number) => void
  alQuitar: () => void
}

/** Convierte lo tipeado en una cantidad entera; lo que no es un entero no negativo se toma como cero. */
function aCantidad(texto: string): number {
  return /^\d+$/.test(texto.trim()) ? Number(texto.trim()) : 0
}

function aTexto(cantidad: number): string {
  return cantidad === 0 ? '' : String(cantidad)
}

/**
 * Un producto del pedido: cajas y unidades sueltas (D8) y, debajo, las líneas que arman con su
 * bruto. Todo lo que se muestra viene calculado de `domain/ventas/`; acá solo se pinta.
 */
export function ItemDeVenta({
  productoId,
  nombre,
  cajas,
  unidades,
  admiteCajas,
  admiteUnidadesSueltas,
  lineas,
  error,
  avisoDeStock,
  estado,
  alCambiarCajas,
  alCambiarUnidades,
  alQuitar,
}: ItemDeVentaProps) {
  return (
    <Card data-testid={`item-${productoId}`} className="flex flex-col gap-2 text-sm text-primary">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <span className="flex items-center gap-1 font-medium">
          {nombre}
          <Ayuda clave="ventas.cajasYUnidades" />
        </span>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span>Cajas</span>
            <input
              aria-label={`Cajas de ${nombre}`}
              className={CLASE_CANTIDAD}
              inputMode="numeric"
              placeholder="0"
              disabled={!admiteCajas}
              value={aTexto(cajas)}
              onChange={(evento) => alCambiarCajas(aCantidad(evento.target.value))}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span>Unidades sueltas</span>
            <input
              aria-label={`Unidades sueltas de ${nombre}`}
              className={CLASE_CANTIDAD}
              inputMode="numeric"
              placeholder="0"
              disabled={!admiteUnidadesSueltas}
              value={aTexto(unidades)}
              onChange={(evento) => alCambiarUnidades(aCantidad(evento.target.value))}
            />
          </label>
          <Boton variante="peligro" aria-label={`Quitar ${nombre}`} onClick={alQuitar}>
            Quitar
          </Boton>
        </div>
      </div>
      {estado && <p className="text-primary/70">{estado}</p>}
      {error && <p className="text-danger">{error}</p>}
      {avisoDeStock && <p className="text-danger">{avisoDeStock}</p>}
      <ul className="flex flex-col gap-1">
        {lineas.map((visible) => (
          <li key={visible.linea.lineaId} className="flex flex-wrap justify-between gap-2">
            <span>
              {textoDeCantidadDeLinea({
                cantidad: visible.linea.cantidad,
                presentacion_nombre: visible.presentacionNombre,
                cantidad_base: visible.cantidadBase,
              })}
            </span>
            <span>{formatearMonto(visible.linea.importeBruto)}</span>
          </li>
        ))}
      </ul>
    </Card>
  )
}
