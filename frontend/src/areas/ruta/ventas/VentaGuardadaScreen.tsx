import { Link, useParams } from 'react-router-dom'

import { Ayuda } from '../../../components/ui/Ayuda'
import { Badge } from '../../../components/ui/Badge'
import { Card } from '../../../components/ui/Card'
import { formatearDinero } from '../../../domain/ruta/lecturasLocales'
import { formatearFechaHora } from '../../../lib/fecha'
import { motivoDeNoAnularDeDatos, useDatosParaAnular } from '../datos/anulacion'
import { useVentaLocal } from '../datos/ventas'
import { useExplicacionDeEnvio, useExplicacionDeOperacion } from '../datos/sincronizacion'
import type { AnulacionLocal, VentaLocal } from '../../../lib/dispositivo/db'
import { MarcaDeRechazoResuelto } from '../sincronizacion/MarcaDeRechazoResuelto'
import { NotaSinSenal } from './NotaSinSenal'
import {
  claveDeAyudaDeEnvio,
  claveDeAyudaDeEnvioDeAnulacion,
  estaAnulada,
  ETIQUETA_ANULADA,
  etiquetaDeEnvio,
} from './presentacionDeVentas'

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
 * Sección «Anulación» (change 22d, D10, D11; VTA-20, VTA-22, SYN-06, SYN-07): motivo, observación,
 * destino de lo cobrado, estado de envío y, si volvió con observaciones o rechazada, su explicación
 * traducida por el tipo de operación. Todo sale de Dexie, con o sin conexión.
 */
function SeccionDeAnulacion({ anulacion }: { anulacion: AnulacionLocal }) {
  const explicacion = useExplicacionDeOperacion(anulacion.operation_id, anulacion.estado_envio)
  const claveDeEstado = claveDeAyudaDeEnvioDeAnulacion(anulacion.estado_envio)
  return (
    <Card role="region" aria-label="Anulación" className="flex flex-col gap-1 text-sm text-primary">
      <h2 className="text-sm font-semibold">Anulación</h2>
      <span className="flex items-center gap-1">
        <Badge variante={anulacion.estado_envio === 'RECHAZADA' ? 'negativo' : 'neutral'}>
          {etiquetaDeEnvio(anulacion.estado_envio)}
        </Badge>
        {claveDeEstado !== null && <Ayuda clave={claveDeEstado} />}
      </span>
      <MarcaDeRechazoResuelto operationId={anulacion.operation_id} estado={anulacion.estado_envio} conAyuda />
      <p className="text-xs text-primary/70">{formatearFechaHora(anulacion.occurred_at).trim()}</p>
      <p className="break-words font-medium">{anulacion.motivo_nombre}</p>
      {anulacion.observacion !== null && <p className="break-words">{anulacion.observacion}</p>}
      {anulacion.devuelve_dinero === true && <p>Se devolvió lo cobrado.</p>}
      {anulacion.devuelve_dinero === false && <p>Lo cobrado quedó a favor del cliente.</p>}
      {explicacion?.tipo === 'rechazo' && (
        <>
          <p className="flex items-start gap-1 break-words">
            {explicacion.texto}
            <Ayuda clave="ruta.observacionesYRechazos" />
          </p>
          {explicacion.codigo !== null && <p className="text-xs font-medium text-danger">{explicacion.codigo}</p>}
          <p className="text-xs text-primary/70">{explicacion.aviso}</p>
        </>
      )}
      {explicacion?.tipo === 'sin_detalle' && (
        <p className="flex items-start gap-1 break-words">
          {explicacion.texto}
          <Ayuda clave="ruta.observacionesYRechazos" />
        </p>
      )}
      {explicacion?.tipo === 'observaciones' && (
        <div className="flex items-start gap-1">
          <ul className="flex list-disc flex-col gap-1 pl-4">
            {explicacion.textos.map((texto, i) => (
              <li key={i} className="break-words">
                {texto}
              </li>
            ))}
          </ul>
          <Ayuda clave="ruta.observacionesYRechazos" />
        </div>
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

  return <DetalleDeVenta venta={lectura.venta} />
}

function DetalleDeVenta({ venta }: { venta: VentaLocal }) {
  const paraAnular = useDatosParaAnular(venta.venta_id)
  const anulacion = paraAnular.estado === 'lista' ? paraAnular.anulacion : null
  const anulada = estaAnulada(anulacion)
  const puedeAnular = paraAnular.estado === 'lista' && motivoDeNoAnularDeDatos(paraAnular) === null
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
        <MarcaDeRechazoResuelto operationId={venta.operation_id} estado={venta.estado_envio} conAyuda />
        {anulada && <Badge variante="negativo">{ETIQUETA_ANULADA}</Badge>}
      </div>
      <Card className="flex flex-col gap-1 text-sm text-primary">
        <p className="break-words">{cliente}</p>
        <p className="text-xs text-primary/70">{formatearFechaHora(venta.occurred_at).trim()}</p>
        <p className="text-base font-semibold">{formatearDinero(venta.calculo.total)}</p>
      </Card>
      <ExplicacionDeLaVenta venta={venta} />
      {anulacion !== null && <SeccionDeAnulacion anulacion={anulacion} />}
      {puedeAnular && (
        <div className="flex items-center gap-1">
          <Link to={`/ruta/ventas/${venta.venta_id}/anular`} className={CLASE_ENLACE}>
            Anular venta
          </Link>
          <Ayuda clave="ruta.anularVenta" />
        </div>
      )}
      <NotaSinSenal venta={venta} anulacion={anulada ? anulacion : null} />
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
