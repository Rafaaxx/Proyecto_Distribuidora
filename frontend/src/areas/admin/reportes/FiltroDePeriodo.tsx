import { useState } from 'react'

import { Campo } from '../../../components/ui/Field'
import { esquemaPeriodo } from '../../../domain/cuentas-corrientes/periodoSchema'
import { textoDePeriodo } from '../../../domain/reportes/presentacion'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

export interface FiltroDePeriodoProps {
  /** El período que aplicó el servidor (D1): los campos arrancan con él y se lo muestra como «Período: …». */
  periodo: { desde: string; hasta: string } | undefined
  desde: string | undefined
  hasta: string | undefined
  /** Solo se llama con un período válido (`desde` no posterior a `hasta`); un campo vacío viaja como `undefined`. */
  onCambio: (periodo: { desde: string | undefined; hasta: string | undefined }) => void
}

/**
 * «Desde» y «Hasta» de los reportes con período (change 26, tarea 10.1; D1, D11, D12; TR-04). Los campos abren con
 * el período del servidor (el mes en curso) y cada cambio recalcula el reporte. Valida con el esquema del estado
 * de cuenta antes de pedir: un rango invertido muestra su texto y no se envía (el servidor sigue siendo la fuente
 * de verdad, `RANGO_DE_FECHAS_INVALIDO`).
 */
export function FiltroDePeriodo({ periodo, desde, hasta, onCambio }: FiltroDePeriodoProps) {
  const [elegidoDesde, setElegidoDesde] = useState<string | null>(null)
  const [elegidoHasta, setElegidoHasta] = useState<string | null>(null)
  const [error, setError] = useState<string | undefined>(undefined)

  const valorDesde = elegidoDesde ?? desde ?? periodo?.desde ?? ''
  const valorHasta = elegidoHasta ?? hasta ?? periodo?.hasta ?? ''

  const cambiar = (nuevoDesde: string, nuevoHasta: string) => {
    setElegidoDesde(nuevoDesde)
    setElegidoHasta(nuevoHasta)
    const validacion = esquemaPeriodo.safeParse({ desde: nuevoDesde, hasta: nuevoHasta })
    if (!validacion.success) {
      setError(validacion.error.issues[0]?.message)
      return
    }
    setError(undefined)
    onCambio({ desde: nuevoDesde || undefined, hasta: nuevoHasta || undefined })
  }

  return (
    <>
      <Campo id="filtro-desde" etiqueta="Desde" ayuda="reportes.periodo">
        <input
          id="filtro-desde"
          type="date"
          className={CLASE_CONTROL}
          value={valorDesde}
          onChange={(e) => cambiar(e.target.value, valorHasta)}
        />
      </Campo>
      <Campo id="filtro-hasta" etiqueta="Hasta" error={error}>
        <input
          id="filtro-hasta"
          type="date"
          className={CLASE_CONTROL}
          value={valorHasta}
          onChange={(e) => cambiar(valorDesde, e.target.value)}
        />
      </Campo>
      {periodo !== undefined && (
        <p className="self-end pb-1 text-sm text-primary/70">{textoDePeriodo(periodo.desde, periodo.hasta)}</p>
      )}
    </>
  )
}
