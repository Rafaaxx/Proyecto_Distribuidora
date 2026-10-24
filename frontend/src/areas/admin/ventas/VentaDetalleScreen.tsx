import { Link, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Badge } from '../../../components/ui/Badge'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { formatearMonto } from '../../../domain/cuentas-corrientes/presentacion'
import {
  detalleDeObservacionDeVenta,
  etiquetaDeEstadoDeFacturacion,
  etiquetaDeEstadoDeVenta,
  etiquetaDeModoDeConfirmacion,
  etiquetaDeObservacionDeVenta,
  etiquetaDePoliticaDeCredito,
  etiquetaDeResolucionDeCredito,
  observacionesDeLineaDeVenta,
  observacionesGeneralesDeVenta,
  textoDeCantidadDeLinea,
  textoDeDescuentoCongelado,
  type ObservacionDeVenta,
} from '../../../domain/ventas/presentacion'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { usePermisos } from '../../../features/identidad/usePermisos'
import type { VentaDetalle } from '../../../features/ventas/api'
import { ErrorDeVentas, PermisoRequeridoVentasError } from '../../../features/ventas/errores'
import { useVenta } from '../../../features/ventas/hooks'
import { formatearFechaHora } from '../../../lib/fecha'
import { formatearCosto, parsearImporteDesdeApi } from '../../../lib/money'
import { VentasSinPermiso } from './VentasSinPermiso'

const TITULO = 'Venta'

/**
 * Detalle de una venta (change 18a, tarea 12.3; spec `administracion-de-ventas`): la venta como
 * quedó congelada, con sus líneas en su presentación, totales, cobranza enlazada, lista y versión
 * con motivo y observaciones junto a su línea. Lo ve quien tiene `VENDER` o `ANULAR_VENTA` (D19).
 * Los costos de cada línea llegan nulos sin `VER_COSTOS` y entonces no se muestra ninguna señal de
 * costo; la utilidad no es de esta pantalla sino de los reportes (REP-04).
 */
export function VentaDetalleScreen() {
  return (
    <SiTienePermiso permiso={['VENDER', 'ANULAR_VENTA']} fallback={<VentasSinPermiso titulo={TITULO} />}>
      <DetalleDeVenta />
    </SiTienePermiso>
  )
}

function DetalleDeVenta() {
  const { ventaId } = useParams<{ ventaId: string }>()
  const venta = useVenta(ventaId)

  if (venta.isPending) {
    return (
      <main>
        <p>Cargando…</p>
      </main>
    )
  }
  if (venta.isError) {
    if (venta.error instanceof PermisoRequeridoVentasError) return <VentasSinPermiso titulo={TITULO} />
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo={TITULO} />
        <Alert>
          {venta.error instanceof ErrorDeVentas && venta.error.codigo === 'RECURSO_NO_ENCONTRADO'
            ? 'No se encontró la venta.'
            : 'No se pudo obtener la venta.'}
        </Alert>
      </main>
    )
  }
  return <VentaCompleta datos={venta.data} />
}

function VentaCompleta({ datos }: { datos: VentaDetalle }) {
  const { tiene } = usePermisos()
  const veCostos = tiene('VER_COSTOS')
  const puedeLeerCobranzas = tiene('REGISTRAR_COBRANZA') || tiene('ANULAR_COBRANZA')
  const observaciones: ObservacionDeVenta[] = datos.observaciones
  const generales = observacionesGeneralesDeVenta(observaciones)

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={`${TITULO} ${datos.numero}`} />

      <Card data-testid="cabecera-de-la-venta" className="flex flex-col gap-1 text-sm text-primary">
        <p>
          Fecha: {formatearFechaHora(datos.occurred_at)} · Cliente: {datos.cliente_nombre ?? datos.cliente_id} · Vendedor:{' '}
          {datos.usuario_nombre ?? datos.usuario_id}
        </p>
        <p>
          Ubicación: {datos.ubicacion_nombre ?? datos.ubicacion_id} ·{' '}
          <Badge variante={datos.estado === 'ANULADA' ? 'negativo' : 'positivo'}>{etiquetaDeEstadoDeVenta(datos.estado)}</Badge> ·{' '}
          {etiquetaDeModoDeConfirmacion(datos.modo_confirmacion)} · {etiquetaDeEstadoDeFacturacion(datos.estado_facturacion)}
        </p>
        {datos.jornada_id ? (
          <p>
            Jornada:{' '}
            <Link to={`/admin/ventas?jornada=${datos.jornada_id}`} className="text-primary/70 hover:text-primary hover:underline">
              Ver las ventas de esta jornada
            </Link>
          </p>
        ) : (
          <p>Jornada: sin jornada</p>
        )}
      </Card>

      <Card data-testid="lista-de-la-venta" className="flex flex-col gap-1 text-sm text-primary">
        <p>
          Lista: {datos.lista_nombre ?? datos.lista_id} · Versión {datos.version_numero ?? datos.version_id}
        </p>
        {datos.motivo_lista && <p>Motivo: {datos.motivo_lista.nombre ?? datos.motivo_lista.motivo_id}</p>}
      </Card>

      <Card className="flex flex-col gap-3 text-sm text-primary">
        <div className="flex items-center gap-1">
          <h2 className="text-base font-semibold">Líneas</h2>
          {veCostos && <Ayuda clave="ventas.costo" />}
        </div>
        {datos.lineas.map((linea) => (
          <div key={linea.linea_id} data-testid={`linea-${linea.linea_id}`} className="flex flex-col gap-1 border-b border-border pb-2 last:border-b-0">
            <div className="flex flex-wrap justify-between gap-2">
              <span className="font-medium">{linea.producto_nombre ?? linea.producto_id}</span>
              <span>{formatearMonto(linea.importe_neto)}</span>
            </div>
            <p>{textoDeCantidadDeLinea(linea)}</p>
            <p className="text-primary/70">
              Precio de referencia {formatearMonto(linea.precio_referencia)} por {String(linea.unidades_referencia)}{' '}
              {linea.unidades_referencia === 1 ? 'unidad' : 'unidades'} · Bruto {formatearMonto(linea.importe_bruto)}
              {parsearImporteDesdeApi(linea.importe_descuento).isZero() ? '' : ` · Descuento ${formatearMonto(linea.importe_descuento)}`}
            </p>
            {linea.descuentos.map((descuento, indice) => (
              <p key={`${descuento.origen}-${String(indice)}`} data-testid={`descuento-${linea.linea_id}-${String(indice)}`}>
                {textoDeDescuentoCongelado(descuento)}
              </p>
            ))}
            {veCostos &&
              (linea.costo_unitario !== null && linea.costo_total !== null ? (
                <p>
                  Costo unitario: {formatearCosto(parsearImporteDesdeApi(linea.costo_unitario))} · Costo total:{' '}
                  {formatearMonto(linea.costo_total)}
                </p>
              ) : (
                <p className="text-primary/70">Sin costo informado</p>
              ))}
            {observacionesDeLineaDeVenta(observaciones, linea.linea_id).map((observacion) => (
              <AvisoDeObservacion key={observacion.codigo} observacion={observacion} />
            ))}
          </div>
        ))}
      </Card>

      <Card className="flex flex-col gap-1 text-sm text-primary">
        <p>
          Neto {formatearMonto(datos.total_neto)} · IVA {formatearMonto(datos.total_iva)}
        </p>
        <p data-testid="total-de-la-venta" className="text-base font-semibold">
          Total: {formatearMonto(datos.total)}
        </p>
      </Card>

      {datos.credito != null && (
        <Card data-testid="credito-de-la-venta" className="flex flex-col gap-1 text-sm text-primary">
          <div className="flex items-center gap-1">
            <h2 className="text-base font-semibold">Crédito del cliente al vender</h2>
            <Ayuda clave="ventas.credito" />
          </div>
          <p>
            Límite {datos.credito.limite === null ? 'sin límite' : formatearMonto(datos.credito.limite)} · Debía{' '}
            {datos.credito.saldo_considerado === null ? '—' : formatearMonto(datos.credito.saldo_considerado)} · Disponible{' '}
            {datos.credito.disponible === null ? '—' : formatearMonto(datos.credito.disponible)}
          </p>
          <p>
            Exceso {datos.credito.exceso === null ? '—' : formatearMonto(datos.credito.exceso)} · Política{' '}
            {datos.credito.politica === null ? '—' : etiquetaDePoliticaDeCredito(datos.credito.politica)}
          </p>
          <p data-testid="credito-resolucion">
            {etiquetaDeResolucionDeCredito(datos.credito.resolucion)}
            {datos.credito.autorizador_nombre ? ` · autorizó ${datos.credito.autorizador_nombre}` : ''}
          </p>
        </Card>
      )}

      <Card data-testid="cobranza-de-la-venta" className="flex flex-col gap-1 text-sm text-primary">
        <h2 className="text-base font-semibold">Cobranza en el acto</h2>
        {datos.cobranza === null ? (
          <p>Sin cobranza en el acto.</p>
        ) : (
          <p>
            {formatearMonto(datos.cobranza.importe)}
            {datos.cobranza.estado === 'ANULADA' ? ' (anulada)' : ''}
            {puedeLeerCobranzas && (
              <>
                {' · '}
                <Link to={`/admin/cobranzas/${datos.cobranza.cobranza_id}`} className="text-primary/70 hover:text-primary hover:underline">
                  Ver la cobranza
                </Link>
              </>
            )}
          </p>
        )}
      </Card>

      {generales.length > 0 && (
        <Card data-testid="observaciones-generales" className="flex flex-col gap-2 text-sm text-primary">
          <div className="flex items-center gap-1">
            <h2 className="text-base font-semibold">Observaciones</h2>
            <Ayuda clave="ventas.observaciones" />
          </div>
          {generales.map((observacion, indice) => (
            <AvisoDeObservacion key={`${observacion.codigo}-${String(indice)}`} observacion={observacion} />
          ))}
        </Card>
      )}
    </main>
  )
}

function AvisoDeObservacion({ observacion }: { observacion: ObservacionDeVenta }) {
  const detalle = detalleDeObservacionDeVenta(observacion)
  return (
    <p className="flex flex-wrap items-center gap-2 text-primary">
      <Badge variante="negativo">{etiquetaDeObservacionDeVenta(observacion.codigo)}</Badge>
      {detalle && <span>{detalle}</span>}
    </p>
  )
}

export default VentaDetalleScreen
