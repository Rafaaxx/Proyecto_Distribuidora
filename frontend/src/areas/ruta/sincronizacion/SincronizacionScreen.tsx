import { Link } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Card } from '../../../components/ui/Card'
import type { ClaveDeAyuda } from '../../../ayuda/textos'
import { formatearDinero } from '../../../domain/ruta/lecturasLocales'
import { NOMBRE_DE_LA_ENTREGA, resumenDeObservaciones } from '../../../domain/ruta/textosDeSincronizacion'
import { useConectado } from '../../../lib/conexion'
import {
  useAnulacionesConProblemas,
  useCobranzasConProblemas,
  useEntregaDelDia,
  useResumenDeSincronizacion,
  useVentasConProblemas,
  type AnulacionConProblema,
  type CobranzaConProblema,
  type VentaConProblema,
} from '../datos/sincronizacion'
import { etiquetaDeEnvio } from '../ventas/presentacionDeVentas'
import { useRechazosResueltos } from '../datos/rechazosResueltos'
import { BotonSincronizar } from './BotonSincronizar'
import { MarcaDeRechazoResuelto } from './MarcaDeRechazoResuelto'
import {
  hayRechazoResuelto,
  textoDePendientes,
  textoDeUltimaSincronizacion,
  textoDelUltimoError,
} from './presentacion'

/**
 * Pantalla «Sincronización» (change 22b, tarea 10.2; `design.md` D8; SYN-04, SYN-06, SYN-09,
 * `02` §12.3, §13.3): conexión, ventas sin enviar, última sincronización, último error con su
 * texto y su código, el botón «Sincronizar» y las ventas «Con observaciones» y «Rechazadas», cada
 * una con su detalle. Lee de la base local; sin lógica de negocio. Change 22d (D10): también lista
 * las anulaciones «Con observaciones» y «Rechazadas» como «Anulación de {número}», con el acceso
 * al detalle de la venta, y lo pendiente cuenta ventas y anulaciones. Change 23 (D10): también las
 * cobranzas «Con observaciones» y «Rechazadas» como «Cobranza a {cliente}», con el acceso a su detalle.
 */
function FilaDeVenta({ item }: { item: VentaConProblema }) {
  const { venta, codigo, explicacion } = item
  const rechazada = venta.estado_envio === 'RECHAZADA'
  const resumen = explicacion?.tipo === 'observaciones' ? resumenDeObservaciones(explicacion.textos) : null
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
          <MarcaDeRechazoResuelto operationId={venta.operation_id} estado={venta.estado_envio} />
          {rechazada && codigo !== null && <span className="text-xs font-medium text-danger">{codigo}</span>}
        </span>
        {explicacion?.tipo === 'rechazo' && (
          <>
            <span className="break-words text-sm text-primary">{explicacion.texto}</span>
            <span className="break-words text-xs text-primary/70">{explicacion.aviso}</span>
          </>
        )}
        {explicacion?.tipo === 'sin_detalle' && (
          <span className="break-words text-sm text-primary">{explicacion.texto}</span>
        )}
        {resumen !== null && (
          <>
            <span className="break-words text-sm text-primary">{resumen.primera}</span>
            {resumen.mas !== null && <span className="text-xs text-primary/70">{resumen.mas}</span>}
          </>
        )}
      </Link>
    </li>
  )
}

function FilaDeAnulacion({ item }: { item: AnulacionConProblema }) {
  const { anulacion, venta, codigo, explicacion } = item
  const rechazada = anulacion.estado_envio === 'RECHAZADA'
  const resumen = explicacion?.tipo === 'observaciones' ? resumenDeObservaciones(explicacion.textos) : null
  return (
    <li className="rounded-md border border-border bg-surface">
      <Link to={`/ruta/ventas/${anulacion.venta_id}`} className="flex min-w-0 flex-col gap-1 p-3">
        <span className="text-sm font-semibold text-primary">Anulación de {venta?.numero ?? '—'}</span>
        <span className="break-words text-sm text-primary">{venta?.nota?.cliente.nombre ?? '—'}</span>
        <span className="flex flex-wrap items-center gap-2">
          <Badge variante={rechazada ? 'negativo' : 'neutral'}>{etiquetaDeEnvio(anulacion.estado_envio)}</Badge>
          <MarcaDeRechazoResuelto operationId={anulacion.operation_id} estado={anulacion.estado_envio} />
          {rechazada && codigo !== null && <span className="text-xs font-medium text-danger">{codigo}</span>}
        </span>
        {explicacion?.tipo === 'rechazo' && (
          <>
            <span className="break-words text-sm text-primary">{explicacion.texto}</span>
            <span className="break-words text-xs text-primary/70">{explicacion.aviso}</span>
          </>
        )}
        {explicacion?.tipo === 'sin_detalle' && (
          <span className="break-words text-sm text-primary">{explicacion.texto}</span>
        )}
        {resumen !== null && (
          <>
            <span className="break-words text-sm text-primary">{resumen.primera}</span>
            {resumen.mas !== null && <span className="text-xs text-primary/70">{resumen.mas}</span>}
          </>
        )}
      </Link>
    </li>
  )
}

function FilaDeCobranza({ item }: { item: CobranzaConProblema }) {
  const { cobranza, codigo, explicacion } = item
  const rechazada = cobranza.estado_envio === 'RECHAZADA'
  const resumen = explicacion?.tipo === 'observaciones' ? resumenDeObservaciones(explicacion.textos) : null
  return (
    <li className="rounded-md border border-border bg-surface">
      <Link to={`/ruta/cobranzas/${cobranza.cobranza_id}`} className="flex min-w-0 flex-col gap-1 p-3">
        <span className="flex flex-wrap items-center justify-between gap-2">
          <span className="break-words text-sm font-semibold text-primary">Cobranza a {cobranza.cliente_nombre ?? '—'}</span>
          <span className="text-sm font-semibold text-primary">{formatearDinero(cobranza.total)}</span>
        </span>
        <span className="flex flex-wrap items-center gap-2">
          <Badge variante={rechazada ? 'negativo' : 'neutral'}>{etiquetaDeEnvio(cobranza.estado_envio ?? 'PENDIENTE')}</Badge>
          <MarcaDeRechazoResuelto operationId={cobranza.operation_id} estado={cobranza.estado_envio ?? 'PENDIENTE'} />
          {rechazada && codigo !== null && <span className="text-xs font-medium text-danger">{codigo}</span>}
        </span>
        {explicacion?.tipo === 'rechazo' && (
          <>
            <span className="break-words text-sm text-primary">{explicacion.texto}</span>
            <span className="break-words text-xs text-primary/70">{explicacion.aviso}</span>
          </>
        )}
        {explicacion?.tipo === 'sin_detalle' && (
          <span className="break-words text-sm text-primary">{explicacion.texto}</span>
        )}
        {resumen !== null && (
          <>
            <span className="break-words text-sm text-primary">{resumen.primera}</span>
            {resumen.mas !== null && <span className="text-xs text-primary/70">{resumen.mas}</span>}
          </>
        )}
      </Link>
      {rechazada && (
        <div className="flex items-center gap-1 px-3 pb-3">
          <Ayuda clave="ruta.cobranzaRechazada" />
        </div>
      )}
    </li>
  )
}

/** Change 24 (D10, D11): la entrega del día con su estado; si fue rechazada, su texto, su código y el aviso. */
function FilaDeEntrega() {
  const entrega = useEntregaDelDia()
  if (entrega === null) return null
  const rechazada = entrega.estado === 'RECHAZADA'
  return (
    <ul className="flex flex-col gap-2">
      <li className="flex min-w-0 flex-col gap-1 rounded-md border border-border bg-surface p-3">
        <span className="text-sm font-semibold text-primary">{NOMBRE_DE_LA_ENTREGA}</span>
        <span className="flex flex-wrap items-center gap-2">
          <Badge variante={rechazada ? 'negativo' : 'neutral'}>{etiquetaDeEnvio(entrega.estado)}</Badge>
          <MarcaDeRechazoResuelto operationId={entrega.operationId} estado={entrega.estado} />
        </span>
        {entrega.explicacion?.tipo === 'rechazo' && (
          <>
            <span className="break-words text-sm text-primary">{entrega.explicacion.texto}</span>
            <span className="break-words text-xs text-primary/70">{entrega.explicacion.aviso}</span>
          </>
        )}
      </li>
    </ul>
  )
}

function Lista({
  titulo,
  clave,
  items,
  anulaciones,
  cobranzas,
  conRechazoResuelto = false,
}: {
  titulo: string
  clave: ClaveDeAyuda
  /** Alguna de las filas está «Resuelta por administración»: se suma su ayuda al título. */
  conRechazoResuelto?: boolean
  items: VentaConProblema[]
  anulaciones: AnulacionConProblema[]
  cobranzas: CobranzaConProblema[]
}) {
  if (items.length === 0 && anulaciones.length === 0 && cobranzas.length === 0) return null
  return (
    <section className="flex flex-col gap-2">
      <h2 className="flex items-center gap-1 text-sm font-semibold text-primary">
        {titulo}
        <Ayuda clave={clave} />
        {conRechazoResuelto && <Ayuda clave="ruta.rechazoResuelto" />}
      </h2>
      <ul className="flex flex-col gap-2">
        {items.map((item) => (
          <FilaDeVenta key={item.venta.venta_id} item={item} />
        ))}
        {anulaciones.map((item) => (
          <FilaDeAnulacion key={item.anulacion.venta_id} item={item} />
        ))}
        {cobranzas.map((item) => (
          <FilaDeCobranza key={item.cobranza.cobranza_id} item={item} />
        ))}
      </ul>
    </section>
  )
}

export function SincronizacionScreen() {
  const conectado = useConectado()
  const resumen = useResumenDeSincronizacion()
  const problemas = useVentasConProblemas()
  const problemasDeAnulacion = useAnulacionesConProblemas()
  const problemasDeCobranza = useCobranzasConProblemas()
  const resueltos = useRechazosResueltos()
  const entrega = useEntregaDelDia()
  const error = resumen.ultimoError === null ? null : textoDelUltimoError(resumen.ultimoError)

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex items-center gap-1">
        <h1 className="text-lg font-semibold text-primary">Sincronización</h1>
        <Ayuda clave="ruta.sincronizar" />
      </div>
      <Card className="flex flex-col gap-2">
        <p className="text-sm text-primary">{conectado ? 'Con conexión' : 'Sin conexión'}</p>
        <p className="text-sm font-semibold text-primary">{textoDePendientes(resumen.sinEnviar, resumen.anulacionesSinEnviar, resumen.cobranzasSinEnviar)}</p>
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
      <FilaDeEntrega />
      {problemas.length + problemasDeAnulacion.length + problemasDeCobranza.length > 0 && (
        <p className="flex items-center gap-1 text-sm text-primary">
          Observaciones y rechazos
          <Ayuda clave="ruta.observacionesYRechazos" />
        </p>
      )}
      <Lista
        titulo="Con observaciones"
        clave="ruta.ventaConObservaciones"
        items={problemas.filter((p) => p.venta.estado_envio === 'CON_OBSERVACIONES')}
        anulaciones={problemasDeAnulacion.filter((p) => p.anulacion.estado_envio === 'CON_OBSERVACIONES')}
        cobranzas={problemasDeCobranza.filter((p) => p.cobranza.estado_envio === 'CON_OBSERVACIONES')}
      />
      <Lista
        titulo="Rechazadas"
        clave="ruta.ventaRechazada"
        items={problemas.filter((p) => p.venta.estado_envio === 'RECHAZADA')}
        anulaciones={problemasDeAnulacion.filter((p) => p.anulacion.estado_envio === 'RECHAZADA')}
        cobranzas={problemasDeCobranza.filter((p) => p.cobranza.estado_envio === 'RECHAZADA')}
        conRechazoResuelto={hayRechazoResuelto(resueltos, [
          ...problemas.map((p) => ({ operationId: p.venta.operation_id, estado: p.venta.estado_envio })),
          ...problemasDeAnulacion.map((p) => ({ operationId: p.anulacion.operation_id, estado: p.anulacion.estado_envio })),
          ...problemasDeCobranza.map((p) => ({ operationId: p.cobranza.operation_id, estado: p.cobranza.estado_envio ?? 'PENDIENTE' })),
          ...(entrega === null ? [] : [{ operationId: entrega.operationId, estado: entrega.estado }]),
        ])}
      />
    </div>
  )
}

export default SincronizacionScreen
