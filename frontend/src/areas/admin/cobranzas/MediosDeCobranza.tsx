import type { ReactNode } from 'react'
import type { UseFormRegisterReturn } from 'react-hook-form'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import type { ClaveDeAyuda } from '../../../ayuda/textos'
import type { MedioDePagoDeFormulario } from '../../../domain/cobranzas/formularioCobranza'
import type { MedioPago } from '../../../features/compras/api'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

export type CampoDeMedio = 'medioPagoId' | 'importe' | 'referencia'

export interface MediosDeCobranzaProps {
  /** Identificadores estables de las filas (`useFieldArray().fields[i].id`). */
  idsDeFilas: readonly string[]
  /** Los medios tal como están hoy en el formulario (`useWatch`). */
  medios: readonly MedioDePagoDeFormulario[]
  mediosDePago: readonly MedioPago[]
  /** `register('medios.<i>.<campo>')` del formulario que lo usa. */
  registrar: (indice: number, campo: CampoDeMedio) => UseFormRegisterReturn
  alAgregar: () => void
  alQuitar: (indice: number) => void
  erroresDeMedio: Readonly<Record<number, string>>
  /** Cobranza independiente: al menos un medio. Venta: la cobranza es opcional y se puede quitar el último. */
  permitirQuitarTodos?: boolean
  /** Lo que va debajo de las filas: la diferencia contra el importe, o la suma cobrada. */
  pie: ReactNode
  titulo?: string
  /** Otro "(?)" del bloque, junto al de los medios (la venta explica su cobranza en el acto). */
  ayudaDelBloque?: ClaveDeAyuda
}

/**
 * Bloque de medios de pago con su suma en vivo, compartido por la cobranza independiente
 * (change 17) y la cobranza en el acto de la venta (change 18a, D12). No tiene lógica: la suma, el
 * faltante y las validaciones viven en `domain/` y las calcula quien lo usa.
 */
export function MediosDeCobranza({
  idsDeFilas,
  medios,
  mediosDePago,
  registrar,
  alAgregar,
  alQuitar,
  erroresDeMedio,
  permitirQuitarTodos = false,
  pie,
  titulo = 'Medios de pago',
  ayudaDelBloque,
}: MediosDeCobranzaProps) {
  const medioDePago = (id: string): MedioPago | undefined => mediosDePago.find((m) => m.id === id)
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-center gap-1">
        <h2 className="text-base font-semibold text-primary">{titulo}</h2>
        {ayudaDelBloque && <Ayuda clave={ayudaDelBloque} />}
        <Ayuda clave="cobranzas.medios" />
      </div>
      {idsDeFilas.map((idDeFila, indice) => {
        const requiereReferencia = medioDePago(medios[indice]?.medioPagoId ?? '')?.requiere_referencia === true
        return (
          <div key={idDeFila} data-testid={`medio-${indice}`} className="flex flex-col gap-2">
            <div className="flex flex-wrap items-end gap-3">
              <Campo id={`medios.${indice}.medioPagoId`} etiqueta="Medio de pago">
                <select id={`medios.${indice}.medioPagoId`} className={CLASE_CONTROL} {...registrar(indice, 'medioPagoId')}>
                  <option value="">Elegí un medio</option>
                  {mediosDePago.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.nombre}
                    </option>
                  ))}
                </select>
              </Campo>
              <Campo id={`medios.${indice}.importe`} etiqueta="Importe del medio">
                <input id={`medios.${indice}.importe`} className={`${CLASE_CONTROL} w-32`} inputMode="decimal" {...registrar(indice, 'importe')} />
              </Campo>
              {requiereReferencia && (
                <Campo id={`medios.${indice}.referencia`} etiqueta="Referencia (obligatoria)">
                  <input id={`medios.${indice}.referencia`} required className={CLASE_CONTROL} {...registrar(indice, 'referencia')} />
                </Campo>
              )}
              {(permitirQuitarTodos || idsDeFilas.length > 1) && (
                <Boton variante="peligro" onClick={() => alQuitar(indice)}>
                  Quitar medio
                </Boton>
              )}
            </div>
            {erroresDeMedio[indice] && <Alert>{erroresDeMedio[indice]}</Alert>}
          </div>
        )
      })}
      <Boton variante="secundario" className="self-start" onClick={alAgregar}>
        Agregar medio
      </Boton>
      {pie}
    </Card>
  )
}
