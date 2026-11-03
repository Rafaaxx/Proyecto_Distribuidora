import { Link, useParams } from 'react-router-dom'

import { Ayuda } from '../../../components/ui/Ayuda'
import { Badge } from '../../../components/ui/Badge'
import { Card } from '../../../components/ui/Card'
import { formatearDinero } from '../../../domain/ruta/lecturasLocales'
import { formatearFechaHora } from '../../../lib/fecha'
import { useVentaLocal } from '../datos/ventas'
import { useExplicacionDeEnvio } from '../datos/sincronizacion'
import type { VentaLocal } from '../../../lib/dispositivo/db'
import { NotaSinSenal } from './NotaSinSenal'
import { claveDeAyudaDeEnvio, etiquetaDeEnvio } from './presentacionDeVentas'

const CLASE_ENLACE =
  'inline-flex items-center justify-center rounded-md border border-border bg-surface-muted px-3 py-3 text-sm font-medium text-primary hover:bg-surface'

/**
 * Observaciones o motivo del rechazo de la venta (change 22c, D4, D5; SYN-04, SYN-06, SYN-07):
 * sale de la fila de `cola` de la operación, sin conexión. Una «Enviada» no muestra nada.
 */
function ExplicacionDeLaVenta({ venta }: { venta: VentaLocal }) {
  const explicacion = useExplicacionDeEnvio(venta)
  if (explicacion === undefined || explicacion === null) return null
  if (explicacion.tipo === 'rechazo') {
    return (
      <Card className="flex flex-col gap-1 text-sm text-primary">
        <h2 className="flex items-center gap-1 text-sm font-semibold">
          Motivo del rechazo
          <Ayuda clave="ruta.observacionesYRechazos" />
        </h2>
        <p className="break-words">{explicacion.texto}</p>
        {explicacion.codigo !== null && <p className="text-xs font-medium text-danger">{explicacion.codigo}</p>}
        <p className="text-xs text-primary/70">{explicacion.aviso}</p>
      </Card>
    )
  }
  return (
    <Card className="flex flex-col gap-1 text-sm text-primary">
      <h2 className="flex items-center gap-1 text-sm font-semibold">
        Observaciones
        <Ayuda clave="ruta.observacionesYRechazos" />
      </h2>
      {explicacion.tipo === 'sin_detalle' ? (
        <p className="break-words">{explicacion.texto}</p>
      ) : (
        <ul className="flex list-disc flex-col gap-1 pl-4">
          {explicacion.textos.map((texto, i) => (
            <li key={i} className="break-words">
              {texto}
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

/**
 * Venta guardada en el teléfono (change 22a, tarea 10.3; `design.md` D13, D14; VTA-06): número
 * asignado al confirmar, total, estado de envío ("Sin enviar"), las acciones de la nota y "Nueva
 * venta". También es el detalle que abre "Ventas de hoy". Lee de Dexie, con o sin conexión.
 */
export function VentaGuardadaScreen() {
  const { id = '' } = useParams()
  const lectura = useVentaLocal(id)

  if (lectura.estado === 'cargando') return <p className="text-sm text-primary">Cargando…</p>
  if (lectura.estado === 'no_encontrada') {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-primary">No encontramos esa venta en este teléfono.</p>
        <Link to="/ruta/ventas" className="text-sm underline">
          Ventas de hoy
        </Link>
      </div>
    )
  }

  const { venta } = lectura
  const cliente = venta.nota?.cliente.nombre ?? '—'
  const claveDeEstado = claveDeAyudaDeEnvio(venta.estado_envio)
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-lg font-semibold text-primary">Venta {venta.numero}</h1>
        <Ayuda clave="ruta.numeroDeVenta" />
        <span className="flex items-center gap-1">
          <Badge>{etiquetaDeEnvio(venta.estado_envio)}</Badge>
          {claveDeEstado !== null && <Ayuda clave={claveDeEstado} />}
        </span>
      </div>
      <Card className="flex flex-col gap-1 text-sm text-primary">
        <p className="break-words">{cliente}</p>
        <p className="text-xs text-primary/70">{formatearFechaHora(venta.occurred_at).trim()}</p>
        <p className="text-base font-semibold">{formatearDinero(venta.calculo.total)}</p>
      </Card>
      <ExplicacionDeLaVenta venta={venta} />
      <NotaSinSenal venta={venta} />
      <div className="grid grid-cols-2 gap-2">
        <Link to="/ruta/vender" className={CLASE_ENLACE}>
          Nueva venta
        </Link>
        <Link to="/ruta/ventas" className={CLASE_ENLACE}>
          Ventas de hoy
        </Link>
      </div>
    </div>
  )
}

export default VentaGuardadaScreen
