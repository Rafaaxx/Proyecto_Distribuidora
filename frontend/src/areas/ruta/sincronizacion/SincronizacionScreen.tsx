import { Link } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Card } from '../../../components/ui/Card'
import type { ClaveDeAyuda } from '../../../ayuda/textos'
import { formatearDinero } from '../../../domain/ruta/lecturasLocales'
import { useConectado } from '../../../lib/conexion'
import { useResumenDeSincronizacion, useVentasConProblemas, type VentaConProblema } from '../datos/sincronizacion'
import { etiquetaDeEnvio } from '../ventas/presentacionDeVentas'
import { BotonSincronizar } from './BotonSincronizar'
import {
  TEXTO_DE_VENTA_RECHAZADA,
  textoDeSinEnviar,
  textoDeUltimaSincronizacion,
  textoDelUltimoError,
} from './presentacion'

/**
 * Pantalla «Sincronización» (change 22b, tarea 10.2; `design.md` D8; SYN-04, SYN-06, SYN-09,
 * `02` §12.3, §13.3): conexión, ventas sin enviar, última sincronización, último error con su
 * texto y su código, el botón «Sincronizar» y las ventas «Con observaciones» y «Rechazadas», cada
 * una con su detalle. Lee de la base local; sin lógica de negocio.
 */
function FilaDeVenta({ item }: { item: VentaConProblema }) {
  const { venta, codigo } = item
  const rechazada = venta.estado_envio === 'RECHAZADA'
  return (
    <li className="rounded-md border border-border bg-surface">
      <Link to={`/ruta/ventas/${venta.venta_id}`} className="flex min-w-0 flex-col gap-1 p-3">
        <span className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm font-semibold text-primary">{venta.numero}</span>
          <span className="text-sm font-semibold text-primary">{formatearDinero(venta.calculo.total)}</span>
        </span>
        <span className="break-words text-sm text-primary">{venta.nota?.cliente.nombre ?? '—'}</span>
        <span className="flex flex-wrap items-center gap-2">
          <Badge variante={rechazada ? 'negativo' : 'neutral'}>{etiquetaDeEnvio(venta.estado_envio)}</Badge>
          {rechazada && codigo !== null && <span className="text-xs font-medium text-danger">{codigo}</span>}
        </span>
        {rechazada && <span className="break-words text-sm text-primary">{TEXTO_DE_VENTA_RECHAZADA}</span>}
      </Link>
    </li>
  )
}

function Lista({ titulo, clave, items }: { titulo: string; clave: ClaveDeAyuda; items: VentaConProblema[] }) {
  if (items.length === 0) return null
  return (
    <section className="flex flex-col gap-2">
      <h2 className="flex items-center gap-1 text-sm font-semibold text-primary">
        {titulo}
        <Ayuda clave={clave} />
      </h2>
      <ul className="flex flex-col gap-2">
        {items.map((item) => (
          <FilaDeVenta key={item.venta.venta_id} item={item} />
        ))}
      </ul>
    </section>
  )
}

export function SincronizacionScreen() {
  const conectado = useConectado()
  const resumen = useResumenDeSincronizacion()
  const problemas = useVentasConProblemas()
  const error = resumen.ultimoError === null ? null : textoDelUltimoError(resumen.ultimoError)

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex items-center gap-1">
        <h1 className="text-lg font-semibold text-primary">Sincronización</h1>
        <Ayuda clave="ruta.sincronizar" />
      </div>
      <Card className="flex flex-col gap-2">
        <p className="text-sm text-primary">{conectado ? 'Con conexión' : 'Sin conexión'}</p>
        <p className="text-sm font-semibold text-primary">{textoDeSinEnviar(resumen.sinEnviar)}</p>
        <p className="text-sm text-primary">{textoDeUltimaSincronizacion(resumen.ultimaSincronizacion)}</p>
        {error !== null && (
          <Alert>
            <span>{error.texto}</span>
            {error.codigo !== null && (
              <>
                {' '}
                <span className="font-medium">{error.codigo}</span>
              </>
            )}
          </Alert>
        )}
        <BotonSincronizar />
      </Card>
      <Lista titulo="Con observaciones" clave="ruta.ventaConObservaciones" items={problemas.filter((p) => p.venta.estado_envio === 'CON_OBSERVACIONES')} />
      <Lista titulo="Rechazadas" clave="ruta.ventaRechazada" items={problemas.filter((p) => p.venta.estado_envio === 'RECHAZADA')} />
    </div>
  )
}

export default SincronizacionScreen
