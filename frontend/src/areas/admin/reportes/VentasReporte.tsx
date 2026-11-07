import { Fragment, useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Card } from '../../../components/ui/Card'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import {
  formatearCajas,
  formatearFechaDeNegocio,
  formatearImporteDeReporte,
  formatearMomento,
  formatearUnidades,
  textoDeAnuladas,
  textoDeLineasSinCosto,
} from '../../../domain/reportes/presentacion'
import { PRIMERAS_PAGINAS_DE_VENTAS, type PaginasDeVentas } from '../../../domain/reportes/paginacion'
import type {
  CifrasDeVentas,
  ReporteDeVentas,
  VentaAnulada,
  VentasPorDia,
  VentasPorProducto,
  VentasPorVendedor,
} from '../../../features/reportes/api'
import type { FiltrosDeVentas } from '../../../features/reportes/claves'
import { mensajeDeErrorDeReportes } from '../../../features/reportes/errores'
import { useReporteDeVentas } from '../../../features/reportes/hooks'
import { FiltroDePeriodo } from './FiltroDePeriodo'
import { Paginacion } from './Paginacion'
import { CLASE_CONTROL, Rotulo, Seccion, Tarjeta } from './piezas'
import { usePaginas, useVendedoresVistos } from './usoDeFiltros'

/** Las columnas de cifras que comparten el resumen, el desglose por día y el de vendedor (D3, D5). */
function columnasDeCifras<T extends CifrasDeVentas>(veUtilidad: boolean): ColumnaTabla<T>[] {
  const columnas: ColumnaTabla<T>[] = [
    { clave: 'ventas', encabezado: 'Ventas', render: (f) => formatearUnidades(f.cantidad_ventas) },
    { clave: 'cajas', encabezado: 'Cajas equivalentes', render: (f) => formatearCajas(f.cajas_equivalentes) },
    { clave: 'unidades', encabezado: 'Unidades', render: (f) => formatearUnidades(f.unidades_base) },
    { clave: 'bruto', encabezado: 'Bruto', render: (f) => formatearImporteDeReporte(f.importe_bruto) },
    { clave: 'descuentos', encabezado: 'Descuentos', render: (f) => formatearImporteDeReporte(f.importe_descuento) },
    { clave: 'neto', encabezado: 'Neto', render: (f) => formatearImporteDeReporte(f.importe_neto) },
    { clave: 'iva', encabezado: 'IVA', render: (f) => formatearImporteDeReporte(f.importe_iva) },
    { clave: 'total', encabezado: 'Total', render: (f) => formatearImporteDeReporte(f.total) },
  ]
  if (veUtilidad) {
    columnas.push(
      {
        clave: 'costo',
        encabezado: 'Costo vendido',
        render: (f) => (f.costo_vendido === null ? '' : formatearImporteDeReporte(f.costo_vendido)),
      },
      {
        clave: 'utilidad',
        encabezado: 'Utilidad',
        render: (f) => (f.utilidad === null ? '' : formatearImporteDeReporte(f.utilidad)),
      },
    )
  }
  return columnas
}

function ResumenDelPeriodo({ reporte }: { reporte: ReporteDeVentas }) {
  const { resumen } = reporte
  return (
    <Seccion titulo="Resumen del período">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tarjeta etiqueta="Ventas" valor={formatearUnidades(resumen.cantidad_ventas)} />
        <Tarjeta
          etiqueta="Cajas equivalentes"
          valor={formatearCajas(resumen.cajas_equivalentes)}
          ayuda="reportes.cajasEquivalentes"
        />
        <Tarjeta etiqueta="Unidades" valor={formatearUnidades(resumen.unidades_base)} />
        <Tarjeta etiqueta="Bruto" valor={formatearImporteDeReporte(resumen.importe_bruto)} />
        <Tarjeta etiqueta="Descuentos" valor={formatearImporteDeReporte(resumen.importe_descuento)} />
        <Tarjeta etiqueta="Neto" valor={formatearImporteDeReporte(resumen.importe_neto)} />
        <Tarjeta etiqueta="IVA" valor={formatearImporteDeReporte(resumen.importe_iva)} />
        <Tarjeta etiqueta="Total" valor={formatearImporteDeReporte(resumen.total)} />
        {reporte.ve_utilidad && resumen.costo_vendido !== null && (
          <Tarjeta etiqueta="Costo vendido" valor={formatearImporteDeReporte(resumen.costo_vendido)} />
        )}
        {reporte.ve_utilidad && resumen.utilidad !== null && (
          <Tarjeta etiqueta="Utilidad" valor={formatearImporteDeReporte(resumen.utilidad)} ayuda="reportes.utilidad" />
        )}
      </div>
      {reporte.ve_utilidad && resumen.sin_costo !== null && resumen.sin_costo.lineas > 0 && (
        <p className="flex items-center gap-1 text-sm text-primary/70">
          {textoDeLineasSinCosto(resumen.sin_costo)}
          <Ayuda clave="reportes.lineasSinCosto" />
        </p>
      )}
    </Seccion>
  )
}

/** El desglose por producto: cada fila se despliega con el detalle por presentación (REP-03). */
function PorProducto({ productos }: { productos: readonly VentasPorProducto[] }) {
  const [abiertos, setAbiertos] = useState<ReadonlySet<string>>(new Set())
  const alternar = (id: string) =>
    setAbiertos((actual) => {
      const nuevo = new Set(actual)
      if (nuevo.has(id)) nuevo.delete(id)
      else nuevo.add(id)
      return nuevo
    })

  return (
    <div className="overflow-x-auto">
      <table aria-label="Por producto" className="w-full border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-border">
            {['Código', 'Producto', 'Cajas equivalentes', 'Unidades', 'Neto'].map((encabezado) => (
              <th key={encabezado} className="px-3 py-2 font-medium text-primary">
                {encabezado}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {productos.map((producto) => {
            const abierto = abiertos.has(producto.producto_id)
            return (
              <Fragment key={producto.producto_id}>
                <tr className="border-b border-border">
                  <td className="px-3 py-2">{producto.codigo}</td>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      aria-expanded={abierto}
                      onClick={() => alternar(producto.producto_id)}
                      className="text-left underline"
                    >
                      {producto.nombre}
                    </button>
                  </td>
                  <td className="px-3 py-2">{formatearCajas(producto.cajas_equivalentes)}</td>
                  <td className="px-3 py-2">{formatearUnidades(producto.unidades_base)}</td>
                  <td className="px-3 py-2">{formatearImporteDeReporte(producto.importe_neto)}</td>
                </tr>
                {abierto && (
                  <tr className="border-b border-border bg-surface-muted">
                    <td colSpan={5} className="px-3 py-2">
                      <table aria-label={producto.nombre} className="w-full border-collapse text-left text-sm">
                        <thead>
                          <tr className="border-b border-border">
                            {['Presentación', 'Unidades por presentación', 'Cantidad', 'Unidades'].map((encabezado) => (
                              <th key={encabezado} className="px-3 py-1 font-medium text-primary">
                                {encabezado}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {producto.presentaciones.map((presentacion) => (
                            <tr key={presentacion.presentacion_id}>
                              <td className="px-3 py-1">{presentacion.nombre}</td>
                              <td className="px-3 py-1">{formatearUnidades(presentacion.unidades_presentacion)}</td>
                              <td className="px-3 py-1">{formatearUnidades(presentacion.cantidad)}</td>
                              <td className="px-3 py-1">{formatearUnidades(presentacion.unidades_base)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function textoDeDevolucion(devuelve: boolean | null): string {
  if (devuelve === null) return ''
  return devuelve ? 'Sí' : 'No'
}

/** Las anuladas del período, aparte de los totales (REP-02, D2). */
function Anuladas({
  reporte,
  alCambiarPagina,
}: {
  reporte: ReporteDeVentas
  alCambiarPagina: (pagina: number) => void
}) {
  const { anuladas, periodo } = reporte
  const { ventas } = anuladas
  const columnas: ColumnaTabla<VentaAnulada>[] = [
    { clave: 'numero', encabezado: 'Número', render: (v) => v.numero },
    {
      clave: 'fecha',
      encabezado: 'Fecha de la venta',
      render: (v) => formatearMomento(v.occurred_at, periodo.zona_horaria),
    },
    { clave: 'cliente', encabezado: 'Cliente', render: (v) => v.cliente_nombre },
    { clave: 'vendedor', encabezado: 'Vendedor', render: (v) => v.vendedor_nombre },
    { clave: 'total', encabezado: 'Total', render: (v) => formatearImporteDeReporte(v.total) },
    {
      clave: 'anulada',
      encabezado: 'Anulada el',
      render: (v) => (v.anulada_en === null ? '' : formatearMomento(v.anulada_en, periodo.zona_horaria)),
    },
    { clave: 'motivo', encabezado: 'Motivo', render: (v) => v.motivo ?? '' },
    { clave: 'devuelve', encabezado: 'Se devolvió el dinero', render: (v) => textoDeDevolucion(v.devuelve_dinero) },
  ]
  return (
    <Seccion titulo="Ventas anuladas del período" ayuda="reportes.anuladas">
      {ventas.total_filas === 0 ? (
        <p className="text-sm text-primary/70">Sin ventas anuladas en el período.</p>
      ) : (
        <>
          <p className="text-sm text-primary/70">{textoDeAnuladas(anuladas.cantidad, anuladas.total)}</p>
          <div className="overflow-x-auto">
            <Tabla
              etiqueta="Ventas anuladas del período"
              filas={ventas.filas}
              columnas={columnas}
              obtenerClave={(v) => v.venta_id}
            />
          </div>
          <Paginacion
            pagina={ventas.pagina}
            paginas={ventas.paginas}
            alCambiar={alCambiarPagina}
            etiqueta="Ventas anuladas del período"
          />
        </>
      )}
    </Seccion>
  )
}

function Desgloses({
  reporte,
  alCambiarPagina,
}: {
  reporte: ReporteDeVentas
  alCambiarPagina: (lista: keyof PaginasDeVentas, pagina: number) => void
}) {
  if (reporte.por_dia.total_filas === 0) {
    return <p className="text-sm text-primary/70">Sin ventas en el período.</p>
  }
  return (
    <>
      <Seccion titulo="Por día">
        <div className="overflow-x-auto">
          <Tabla
            etiqueta="Por día"
            filas={reporte.por_dia.filas}
            columnas={[
              {
                clave: 'fecha',
                encabezado: 'Fecha',
                render: (f: VentasPorDia) => formatearFechaDeNegocio(f.fecha),
              },
              ...columnasDeCifras<VentasPorDia>(reporte.ve_utilidad),
            ]}
            obtenerClave={(f) => f.fecha}
          />
        </div>
        <Paginacion
          pagina={reporte.por_dia.pagina}
          paginas={reporte.por_dia.paginas}
          alCambiar={(pagina) => alCambiarPagina('porDia', pagina)}
          etiqueta="Por día"
        />
      </Seccion>
      <Seccion titulo="Por vendedor">
        <div className="overflow-x-auto">
          <Tabla
            etiqueta="Por vendedor"
            filas={reporte.por_vendedor}
            columnas={[
              {
                clave: 'vendedor',
                encabezado: 'Vendedor',
                render: (f: VentasPorVendedor) => f.vendedor_nombre,
              },
              ...columnasDeCifras<VentasPorVendedor>(reporte.ve_utilidad),
            ]}
            obtenerClave={(f) => f.vendedor_id}
          />
        </div>
      </Seccion>
      <Seccion titulo="Por producto">
        <PorProducto productos={reporte.por_producto.filas} />
        <Paginacion
          pagina={reporte.por_producto.pagina}
          paginas={reporte.por_producto.paginas}
          alCambiar={(pagina) => alCambiarPagina('porProducto', pagina)}
          etiqueta="Por producto"
        />
      </Seccion>
    </>
  )
}

/**
 * Pestaña «Ventas» de `/admin/reportes` (change 26, tarea 10.2; D1, D2, D3, D5, D11, D12; REP-01 a REP-05):
 * filtros de período y vendedor, resumen, desgloses por día, vendedor y producto, la nota de las líneas sin costo
 * y las anuladas aparte. Sin `VER_UTILIDAD` el servidor manda `ve_utilidad: false` y no hay columnas de costo ni
 * utilidad. Los importes se muestran desde su string (INV-03); la pantalla no calcula nada.
 */
export function VentasReporte() {
  const [filtros, setFiltros] = useState<FiltrosDeVentas>({})
  // Cambiar el período o el vendedor vuelve todas las listas a la página 1 (D14).
  const [paginas, irAPagina] = usePaginas(JSON.stringify(filtros), PRIMERAS_PAGINAS_DE_VENTAS)
  const reporte = useReporteDeVentas({
    ...filtros,
    paginaPorDia: paginas.porDia,
    paginaPorProducto: paginas.porProducto,
    paginaAnuladas: paginas.anuladas,
  })
  const datos = reporte.data
  const vendedores = useVendedoresVistos(datos, (d) =>
    d.por_vendedor.map((v) => ({ id: v.vendedor_id, nombre: v.vendedor_nombre })),
  )

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className="flex flex-wrap items-start gap-3">
          <FiltroDePeriodo
            periodo={datos?.periodo}
            desde={filtros.desde}
            hasta={filtros.hasta}
            onCambio={(periodo) => setFiltros((actual) => ({ ...actual, ...periodo }))}
          />
          <Rotulo id="filtro-vendedor" etiqueta="Vendedor">
            <select
              id="filtro-vendedor"
              className={CLASE_CONTROL}
              value={filtros.vendedorId ?? ''}
              onChange={(e) => setFiltros((actual) => ({ ...actual, vendedorId: e.target.value || undefined }))}
            >
              <option value="">Todos</option>
              {[...vendedores.entries()].map(([id, nombre]) => (
                <option key={id} value={id}>
                  {nombre}
                </option>
              ))}
            </select>
          </Rotulo>
        </div>
      </Card>

      {reporte.isPending && <p>Cargando…</p>}
      {reporte.isError && <Alert>{mensajeDeErrorDeReportes(reporte.error)}</Alert>}
      {datos !== undefined && !reporte.isError && (
        <>
          <ResumenDelPeriodo reporte={datos} />
          <Desgloses reporte={datos} alCambiarPagina={irAPagina} />
          <Anuladas reporte={datos} alCambiarPagina={(pagina) => irAPagina('anuladas', pagina)} />
        </>
      )}
    </div>
  )
}

export default VentasReporte
