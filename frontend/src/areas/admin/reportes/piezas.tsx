import type { ReactNode } from 'react'

import type { ClaveDeAyuda } from '../../../ayuda/textos'
import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Card } from '../../../components/ui/Card'
import { mensajeDeErrorDeReportes } from '../../../features/reportes/errores'

/** Piezas que comparten las pestañas de reportes (change 26, D11): solo presentación. */

export const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

/** Una sección de la pestaña: título (con su «(?)» si lleva) y contenido. */
export function Seccion({ titulo, ayuda, children }: { titulo: string; ayuda?: ClaveDeAyuda; children: ReactNode }) {
  return (
    <section aria-label={titulo} className="flex flex-col gap-2">
      <div className="flex items-center gap-1">
        <h2 className="text-base font-semibold text-primary">{titulo}</h2>
        {ayuda && <Ayuda clave={ayuda} />}
      </div>
      {children}
    </section>
  )
}

/** El nombre de la pestaña como título de su contenido, con la ayuda del reporte (D13). */
export function TituloDePestana({ titulo, ayuda }: { titulo: string; ayuda: ClaveDeAyuda }) {
  return (
    <div className="flex items-center gap-1">
      <h2 className="text-lg font-semibold text-primary">{titulo}</h2>
      <Ayuda clave={ayuda} />
    </div>
  )
}

/** Una cifra con su rótulo (resumen del período, totales de los saldos). */
export function Tarjeta({ etiqueta, valor, ayuda }: { etiqueta: string; valor: string; ayuda?: ClaveDeAyuda }) {
  return (
    <Card>
      <dl className="flex flex-col gap-1">
        <dt className="flex items-center gap-1 text-sm text-primary/70">
          {etiqueta}
          {ayuda && <Ayuda clave={ayuda} />}
        </dt>
        <dd className="text-lg font-semibold text-primary">{valor}</dd>
      </dl>
    </Card>
  )
}

export function Rotulo({ id, etiqueta, children }: { id: string; etiqueta: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-primary">
        {etiqueta}
      </label>
      {children}
    </div>
  )
}

/** Cargando o error de un reporte (D12: error de carga con el texto aprobado). */
export function EstadoDelReporte({ cargando, error }: { cargando: boolean; error: unknown }) {
  return (
    <>
      {cargando && <p>Cargando…</p>}
      {error !== null && error !== undefined && <Alert>{mensajeDeErrorDeReportes(error)}</Alert>}
    </>
  )
}

/** Cantidad y total de un renglón de reporte, uno debajo del otro. */
export function CantidadYTotal({ cantidad, total }: { cantidad: number; total: string }) {
  return (
    <div className="flex flex-col">
      <span>{String(cantidad)}</span>
      <span className="text-primary/70">{total}</span>
    </div>
  )
}
