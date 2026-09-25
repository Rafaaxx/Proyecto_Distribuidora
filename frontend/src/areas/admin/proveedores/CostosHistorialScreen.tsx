import { useParams } from 'react-router-dom'

import { Badge } from '../../../components/ui/Badge'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import type { CostoInformado } from '../../../features/proveedores/api'
import { PermisoRequeridoProveedoresError } from '../../../features/proveedores/errores'
import { useCostoVigente, useHistorialDeCostos } from '../../../features/proveedores/useListados'
import { formatearFechaHora } from '../../../lib/fecha'
import {
  formatearCosto,
  formatearImporte,
  formatearPorcentaje,
  parsearImporteDesdeApi,
  redondearCosto,
  redondearImporte,
} from '../../../lib/money'

/**
 * Costo vigente a hoy e historial de costos informados de un producto,
 * de la vigencia más reciente a la más antigua; la vigencia futura se
 * marca como programada (tarea 11.5, spec `administracion-de-proveedores`,
 * escenario "Historial con vigente resaltado", CST-03, TR-04).
 */
export function CostosHistorialScreen() {
  const { productoId } = useParams<{ productoId: string }>()
  const vigente = useCostoVigente(productoId)
  const historial = useHistorialDeCostos(productoId)

  const esErrorDePermiso =
    (vigente.isError && vigente.error instanceof PermisoRequeridoProveedoresError) ||
    (historial.isError && historial.error instanceof PermisoRequeridoProveedoresError)

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Historial de costos" />

      {esErrorDePermiso && <p className="text-sm text-primary/70">No tenés permiso para ver costos.</p>}

      {!esErrorDePermiso && (
        <>
          <section className="flex flex-col gap-2">
            <h2 className="text-base font-semibold text-primary">Costo vigente</h2>
            {vigente.isPending && <p className="text-sm text-primary/70">Cargando…</p>}
            {vigente.isError && <p role="alert">No se pudo obtener el costo vigente.</p>}
            {vigente.isSuccess && (
              <>
                {vigente.data.costo ? (
                  <div className="flex flex-col gap-1 text-sm text-primary">
                    <p className="text-lg font-semibold">
                      {formatearCosto(parsearImporteDesdeApi(vigente.data.costo.costo_base))}
                    </p>
                    <p>
                      <span>{vigente.data.costo.presentacion_nombre}</span> de{' '}
                      <span>{vigente.data.costo.proveedor_nombre}</span>, vigente desde{' '}
                      <span>{vigente.data.costo.vigencia_desde}</span>
                    </p>
                    <p>
                      Informado: <span>{formatearImporte(redondearImporte(vigente.data.costo.valor))}</span>{' '}
                      <span>{vigente.data.costo.incluye_iva ? '(con IVA)' : '(sin IVA)'}</span>
                    </p>
                  </div>
                ) : (
                  <p className="text-sm text-primary">Sin costo vigente</p>
                )}
              </>
            )}
          </section>

          {vigente.isSuccess && vigente.data.por_presentacion.length > 0 && (
            <SeccionUltimoCostoPorPresentacion
              costos={vigente.data.por_presentacion}
              idCostoVigente={vigente.data.costo?.id}
            />
          )}

          <section className="flex flex-col gap-2">
            <h2 className="text-base font-semibold text-primary">Historial</h2>
            {historial.isPending && <p className="text-sm text-primary/70">Cargando…</p>}
            {historial.isError && <p role="alert">No se pudo obtener el historial de costos.</p>}
            {historial.isSuccess && (
              <Card className="overflow-x-auto p-0">
                <table className="w-full border-collapse text-left text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="px-3 py-2 font-medium text-primary">Vigencia desde</th>
                      <th className="px-3 py-2 font-medium text-primary">Proveedor</th>
                      <th className="px-3 py-2 font-medium text-primary">Presentación</th>
                      <th className="px-3 py-2 font-medium text-primary">Informado</th>
                      <th className="px-3 py-2 font-medium text-primary">Bonificación</th>
                      <th className="px-3 py-2 font-medium text-primary">Costo base</th>
                      <th className="px-3 py-2 font-medium text-primary">Alícuota aplicada</th>
                      <th className="px-3 py-2 font-medium text-primary">Registrado por</th>
                      <th className="px-3 py-2 font-medium text-primary">Registrado el</th>
                      <th className="px-3 py-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {historial.data.pages
                      .flatMap((pagina) => pagina.items)
                      .map((costo: CostoInformado) => (
                        <FilaHistorial
                          key={costo.id}
                          costo={costo}
                          hoy={vigente.data?.fecha ?? fechaDeHoy()}
                          esVigente={costo.id === vigente.data?.costo?.id}
                        />
                      ))}
                  </tbody>
                </table>
              </Card>
            )}
          </section>
        </>
      )}
    </main>
  )
}

/** `hoy` es la fecha de negocio de la organización (`CostoVigenteResponse.fecha`,
 * TR-04, `core/clock.py`), no la fecha local del navegador -- así la
 * marca de "programado" coincide con el mismo criterio que resolvió el
 * costo vigente. */
function FilaHistorial({
  costo,
  hoy,
  esVigente,
}: {
  costo: CostoInformado
  hoy: string
  esVigente: boolean
}) {
  const programado = costo.vigencia_desde > hoy

  return (
    <tr className={`border-b border-border last:border-0 ${esVigente ? 'bg-primary/5' : ''}`}>
      <td className="px-3 py-2">{costo.vigencia_desde}</td>
      <td className="px-3 py-2">{costo.proveedor_nombre}</td>
      <td className="px-3 py-2">{costo.presentacion_nombre}</td>
      <td className="px-3 py-2">
        <span>{formatearImporte(redondearImporte(costo.valor))}</span>{' '}
        <span>{costo.incluye_iva ? '(con IVA)' : '(sin IVA)'}</span>
      </td>
      <td className="px-3 py-2">{formatearPorcentaje(redondearCosto(costo.bonificacion))}</td>
      <td className="px-3 py-2">{formatearCosto(parsearImporteDesdeApi(costo.costo_base))}</td>
      <td className="px-3 py-2">{formatearPorcentaje(redondearCosto(costo.alicuota_aplicada))}</td>
      <td className="px-3 py-2">{costo.usuario_nombre}</td>
      <td className="px-3 py-2">{formatearFechaHora(costo.creado_en)}</td>
      <td className="px-3 py-2">
        {/* No solo color: la insignia lleva el estado en el texto. */}
        {esVigente && <Badge variante="positivo">Vigente</Badge>}
        {!esVigente && programado && <Badge variante="neutral">Programado</Badge>}
      </td>
    </tr>
  )
}

/**
 * "Último costo informado por presentación" (P11, `contrato-api.md`,
 * aprobado en la verificación manual 13.5, opción B): muestra, para cada
 * presentación con costo a la fecha, el último costo informado -- ya
 * ordenado por `presentacion_nombre` por el backend. Puramente
 * informativo (nota fija): el precio (PRC-11) sigue calculándose solo con
 * el costo vigente del producto (`vigente.data.costo`), nunca con esta
 * lista. La fila cuyo `id` coincide con el costo vigente se marca con la
 * misma insignia "Vigente" que `FilaHistorial`.
 */
function SeccionUltimoCostoPorPresentacion({
  costos,
  idCostoVigente,
}: {
  costos: CostoInformado[]
  idCostoVigente: string | undefined
}) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-base font-semibold text-primary">Último costo informado por presentación</h2>
      <Card className="overflow-x-auto p-0">
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-3 py-2 font-medium text-primary">Presentación</th>
              <th className="px-3 py-2 font-medium text-primary">Proveedor</th>
              <th className="px-3 py-2 font-medium text-primary">Vigencia desde</th>
              <th className="px-3 py-2 font-medium text-primary">Informado</th>
              <th className="px-3 py-2 font-medium text-primary">Costo base por unidad</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {costos.map((costo) => (
              <tr key={costo.id} className="border-b border-border last:border-0">
                <td className="px-3 py-2">{costo.presentacion_nombre}</td>
                <td className="px-3 py-2">{costo.proveedor_nombre}</td>
                <td className="px-3 py-2">{costo.vigencia_desde}</td>
                <td className="px-3 py-2">
                  <span>{formatearImporte(redondearImporte(costo.valor))}</span>{' '}
                  <span>{costo.incluye_iva ? '(con IVA)' : '(sin IVA)'}</span>
                </td>
                <td className="px-3 py-2">{formatearCosto(parsearImporteDesdeApi(costo.costo_base))}</td>
                <td className="px-3 py-2">
                  {costo.id === idCostoVigente && <Badge variante="positivo">Vigente</Badge>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <p className="text-xs text-primary/70">
        Informativo: el precio se calcula solo con el costo vigente del producto.
      </p>
    </section>
  )
}

function fechaDeHoy(): string {
  const ahora = new Date()
  const anio = ahora.getFullYear()
  const mes = String(ahora.getMonth() + 1).padStart(2, '0')
  const dia = String(ahora.getDate()).padStart(2, '0')
  return `${anio}-${mes}-${dia}`
}

export default CostosHistorialScreen
