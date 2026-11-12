import { Fragment, useState } from 'react'

import { Card } from '../../../components/ui/Card'
import {
  formatearImporteDeReporte,
  formatearUnidades,
  textoDeAjustesAnulados,
} from '../../../domain/reportes/presentacion'
import type { MotivoDeAjuste, ProductoAjustado, ReporteDeAjustes } from '../../../features/reportes/api'
import type { FiltrosDePeriodo } from '../../../features/reportes/claves'
import { useReporteDeAjustes } from '../../../features/reportes/hooks'
import { FiltroDePeriodo } from './FiltroDePeriodo'
import { EstadoDelReporte, TituloDePestana } from './piezas'

/** Lo que tienen en común un motivo, la fila de diferencias de rendición y un producto ajustado. */
interface CifrasDeAjuste {
  entradas: number
  salidas: number
  valor_de_entradas: string | null
  valor_de_salidas: string | null
  unidades_sin_costo: number | null
}

const importeONada = (valor: string | null) => (valor === null ? '' : formatearImporteDeReporte(valor))

/** Las celdas de unidades y, solo con `VER_COSTOS`, las de valor y las unidades sin costo (STK-03, TR-03). */
function CeldasDeCifras({ cifras, veCostos }: { cifras: CifrasDeAjuste; veCostos: boolean }) {
  return (
    <>
      <td className="px-3 py-2">{formatearUnidades(cifras.entradas)}</td>
      <td className="px-3 py-2">{formatearUnidades(cifras.salidas)}</td>
      {veCostos && (
        <>
          <td className="px-3 py-2">{importeONada(cifras.valor_de_entradas)}</td>
          <td className="px-3 py-2">{importeONada(cifras.valor_de_salidas)}</td>
          <td className="px-3 py-2">
            {cifras.unidades_sin_costo === null ? '' : formatearUnidades(cifras.unidades_sin_costo)}
          </td>
        </>
      )}
    </>
  )
}

function EncabezadosDeCifras({ veCostos, conMotivo }: { veCostos: boolean; conMotivo: boolean }) {
  const encabezados = [
    ...(conMotivo ? ['Motivo', 'Ajustes'] : ['Código', 'Producto']),
    'Entradas',
    'Salidas',
    ...(veCostos ? ['Valor de las entradas', 'Valor de las salidas', 'Sin costo'] : []),
  ]
  return (
    <thead>
      <tr className="border-b border-border">
        {encabezados.map((encabezado) => (
          <th key={encabezado} className="px-3 py-2 font-medium text-primary">
            {encabezado}
          </th>
        ))}
      </tr>
    </thead>
  )
}

function DetallePorProducto({ nombre, productos, veCostos }: { nombre: string; productos: ProductoAjustado[]; veCostos: boolean }) {
  return (
    <table aria-label={nombre} className="w-full border-collapse text-left text-sm">
      <EncabezadosDeCifras veCostos={veCostos} conMotivo={false} />
      <tbody>
        {productos.map((producto) => (
          <tr key={producto.producto_id} className="border-b border-border">
            <td className="px-3 py-2">{producto.codigo}</td>
            <td className="px-3 py-2">{producto.nombre}</td>
            <CeldasDeCifras cifras={producto} veCostos={veCostos} />
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/** Una fila de motivo (o la de diferencias de rendición) que se despliega con su detalle por producto. */
function FilaDeMotivo({
  nombre,
  ajustes,
  cifras,
  productos,
  veCostos,
  abierto,
  alternar,
}: {
  nombre: string
  ajustes: number | null
  cifras: CifrasDeAjuste
  productos: ProductoAjustado[]
  veCostos: boolean
  abierto: boolean
  alternar: () => void
}) {
  const columnas = veCostos ? 7 : 4
  return (
    <Fragment>
      <tr className="border-b border-border">
        <td className="px-3 py-2">
          {productos.length === 0 ? (
            nombre
          ) : (
            <button type="button" aria-expanded={abierto} onClick={alternar} className="text-left underline">
              {nombre}
            </button>
          )}
        </td>
        <td className="px-3 py-2">{ajustes === null ? '' : formatearUnidades(ajustes)}</td>
        <CeldasDeCifras cifras={cifras} veCostos={veCostos} />
      </tr>
      {abierto && productos.length > 0 && (
        <tr className="border-b border-border bg-surface-muted">
          <td colSpan={columnas} className="px-3 py-2">
            <DetallePorProducto nombre={nombre} productos={productos} veCostos={veCostos} />
          </td>
        </tr>
      )}
    </Fragment>
  )
}

const sinMovimientos = (r: ReporteDeAjustes) => r.motivos.length === 0 && r.diferencias_de_rendicion.entradas + r.diferencias_de_rendicion.salidas === 0

function Cuerpo({ reporte }: { reporte: ReporteDeAjustes }) {
  const [abiertos, setAbiertos] = useState<ReadonlySet<string>>(new Set())
  const alternar = (clave: string) =>
    setAbiertos((actual) => {
      const nuevo = new Set(actual)
      if (nuevo.has(clave)) nuevo.delete(clave)
      else nuevo.add(clave)
      return nuevo
    })
  const diferencias = reporte.diferencias_de_rendicion

  return (
    <>
      {sinMovimientos(reporte) ? (
        <p className="text-sm text-primary/70">Sin ajustes en el período.</p>
      ) : (
        <div className="overflow-x-auto">
          <table aria-label="Ajustes por motivo" className="w-full border-collapse text-left text-sm">
            <EncabezadosDeCifras veCostos={reporte.ve_costos} conMotivo />
            <tbody>
              {reporte.motivos.map((motivo: MotivoDeAjuste) => (
                <FilaDeMotivo
                  key={motivo.motivo_id}
                  nombre={motivo.motivo_nombre}
                  ajustes={motivo.ajustes}
                  cifras={motivo}
                  productos={motivo.productos}
                  veCostos={reporte.ve_costos}
                  abierto={abiertos.has(motivo.motivo_id)}
                  alternar={() => alternar(motivo.motivo_id)}
                />
              ))}
              <FilaDeMotivo
                nombre="Diferencias de rendición"
                ajustes={null}
                cifras={diferencias}
                productos={diferencias.productos}
                veCostos={reporte.ve_costos}
                abierto={abiertos.has('diferencias')}
                alternar={() => alternar('diferencias')}
              />
            </tbody>
          </table>
        </div>
      )}
      {reporte.ajustes_anulados > 0 && (
        <p className="text-sm text-primary/70">{textoDeAjustesAnulados(reporte.ajustes_anulados)}</p>
      )}
    </>
  )
}

/**
 * Pestaña «Ajustes por motivo» de `/admin/reportes` (change 26, tarea 12.3; D10, D11, D12; STK-03, RUT-06, TR-03):
 * una fila por motivo con su detalle por producto, la fila aparte de «Diferencias de rendición» y la nota de los
 * ajustes anulados. Las columnas de valor y de unidades sin costo solo existen con `VER_COSTOS` (el servidor manda
 * `null` y `ve_costos: false`); las unidades se ven siempre.
 */
export function AjustesPorMotivoReporte() {
  const [filtros, setFiltros] = useState<FiltrosDePeriodo>({})
  const reporte = useReporteDeAjustes(filtros)
  const datos = reporte.data

  return (
    <div className="flex flex-col gap-4">
      <TituloDePestana titulo="Ajustes por motivo" ayuda="reportes.ajustesPorMotivo" />
      <Card>
        <div className="flex flex-wrap items-start gap-3">
          <FiltroDePeriodo
            periodo={datos?.periodo}
            desde={filtros.desde}
            hasta={filtros.hasta}
            onCambio={(periodo) => setFiltros((actual) => ({ ...actual, ...periodo }))}
          />
        </div>
      </Card>

      <EstadoDelReporte cargando={reporte.isPending} error={reporte.error} />
      {datos !== undefined && !reporte.isError && <Cuerpo reporte={datos} />}
    </div>
  )
}

export default AjustesPorMotivoReporte
