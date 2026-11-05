import type { ReferenciaDePresentacion } from '../../../domain/stock/cantidades'
import { CLASE_CONTROL } from './piezasDeOperacion'

/**
 * Piezas compartidas por la pantalla de conteo y el diálogo de cierre (change 24, D9; CAT-08):
 * una cantidad se escribe en cajas + unidades si se conoce la presentación de referencia del
 * producto y en unidades base si no (por ejemplo, un producto agregado como sobrante: la lista de
 * productos que ve `RENDIR_JORNADA` no trae presentaciones). Sin lógica de negocio.
 */
export interface ValorDeCantidad {
  cajas: string
  unidades: string
}

export interface CampoDeCantidadProps {
  /** Nombre del producto: rotula los controles para el lector de pantalla. */
  producto: string
  valor: ValorDeCantidad
  referencia: ReferenciaDePresentacion | null
  onChange: (valor: ValorDeCantidad) => void
}

export function CampoDeCantidad({ producto, valor, referencia, onChange }: CampoDeCantidadProps) {
  const conCajas = referencia !== null && referencia.unidades > 1
  return (
    <div className="flex flex-wrap items-center gap-2">
      {conCajas && (
        <label className="flex items-center gap-1 text-xs text-primary/70">
          {referencia.nombre ?? 'Cajas'}
          <input
            inputMode="numeric"
            autoComplete="off"
            aria-label={`Cajas de ${producto}`}
            className={`${CLASE_CONTROL} w-20`}
            value={valor.cajas}
            onChange={(evento) => onChange({ ...valor, cajas: evento.target.value })}
          />
        </label>
      )}
      <label className="flex items-center gap-1 text-xs text-primary/70">
        {conCajas ? 'Unidades' : 'Unidades base'}
        <input
          inputMode="numeric"
          autoComplete="off"
          aria-label={`Unidades de ${producto}`}
          className={`${CLASE_CONTROL} w-20`}
          value={valor.unidades}
          onChange={(evento) => onChange({ ...valor, unidades: evento.target.value })}
        />
      </label>
    </div>
  )
}
