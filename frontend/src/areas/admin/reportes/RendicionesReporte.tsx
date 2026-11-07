import { useState } from 'react'

import { Card } from '../../../components/ui/Card'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import {
  etiquetaDeEstadoDeJornada,
  formatearImporteDeReporte,
  formatearMomento,
  formatearUnidades,
} from '../../../domain/reportes/presentacion'
import type {
  JornadaDeRendicion,
  ReporteDeRendiciones,
  ResumenDeJornadaDeReporte,
  VendedorDeRendicion,
} from '../../../features/reportes/api'
import type { EstadoDeJornadaFiltro, FiltrosDeRendiciones } from '../../../features/reportes/claves'
import { mensajeDeErrorDeReportes } from '../../../features/reportes/errores'
import { useDetalleDeRendicion, useReporteDeRendiciones } from '../../../features/reportes/hooks'
import { Alert } from '../../../components/ui/Alert'
import { ResumenDeJornadaVista } from '../stock/ResumenDeJornada'
import type { ContextoDelResumen } from '../stock/useContextoDelResumen'
import { referenciaDeRespuesta, type ReferenciaDePresentacion } from '../../../domain/stock/cantidades'
import { FiltroDePeriodo } from './FiltroDePeriodo'
import { Paginacion } from './Paginacion'
import {
  CantidadYTotal,
  CLASE_CONTROL,
  EstadoDelReporte,
  Rotulo,
  Seccion,
  TituloDePestana,
} from './piezas'
import { usePaginas, useVendedoresVistos } from './usoDeFiltros'

type Cobranzas = JornadaDeRendicion['cobranzas']
type Dinero = NonNullable<JornadaDeRendicion['despues_de_la_rendicion']>

/** Los estados que se pueden elegir, en el orden de la vida de una jornada (D7, D12). */
const ESTADOS: readonly EstadoDeJornadaFiltro[] = ['ABIERTA', 'EN_RENDICION', 'CERRADA', 'LIBERADA']

/** Lo cobrado: el total y, debajo, cada medio de pago tal como viene (INV-03). */
function Cobrado({ cobranzas }: { cobranzas: Cobranzas }) {
  return (
    <div className="flex flex-col">
      <CantidadYTotal cantidad={cobranzas.cantidad} total={formatearImporteDeReporte(cobranzas.total)} />
      {cobranzas.por_medio.map((medio) => (
        <span key={medio.medio_pago_id} className="text-primary/70">
          {medio.nombre ?? medio.medio_pago_id}: {formatearImporteDeReporte(medio.total)}
        </span>
      ))}
    </div>
  )
}

/** Lo registrado después de la rendición, aparte de lo vigente (RUT-07, ADR-068). */
function DespuesDeLaRendicion({ dinero }: { dinero: Dinero | null }) {
  if (dinero === null) return null
  const renglones: [string, number, string][] = [
    ['Ventas', dinero.ventas.cantidad, dinero.ventas.total],
    ['Anuladas', dinero.anuladas.cantidad, dinero.anuladas.total],
    ['Cobrado', dinero.cobranzas.cantidad, dinero.cobranzas.total],
  ]
  const presentes = renglones.filter(([, cantidad]) => cantidad > 0)
  return (
    <div className="flex flex-col">
      {presentes.map(([rotulo, cantidad, total]) => (
        <span key={rotulo}>
          {rotulo}: {String(cantidad)} · {formatearImporteDeReporte(total)}
        </span>
      ))}
    </div>
  )
}

function columnasPorVendedor(veCostos: boolean): ColumnaTabla<VendedorDeRendicion>[] {
  const columnas: ColumnaTabla<VendedorDeRendicion>[] = [
    { clave: 'vendedor', encabezado: 'Vendedor', render: (f) => f.vendedor_nombre },
    { clave: 'jornadas', encabezado: 'Jornadas', render: (f) => formatearUnidades(f.jornadas) },
    {
      clave: 'ventas',
      encabezado: 'Ventas',
      render: (f) => <CantidadYTotal cantidad={f.ventas.cantidad} total={formatearImporteDeReporte(f.ventas.total)} />,
    },
    {
      clave: 'anuladas',
      encabezado: 'Anuladas',
      render: (f) => <CantidadYTotal cantidad={f.anuladas.cantidad} total={formatearImporteDeReporte(f.anuladas.total)} />,
    },
    { clave: 'cobrado', encabezado: 'Cobrado', render: (f) => <Cobrado cobranzas={f.cobranzas} /> },
    { clave: 'faltantes', encabezado: 'Faltantes', render: (f) => formatearUnidades(f.faltantes) },
    { clave: 'sobrantes', encabezado: 'Sobrantes', render: (f) => formatearUnidades(f.sobrantes) },
  ]
  if (veCostos) {
    columnas.push({
      clave: 'valor',
      encabezado: 'Valor de las diferencias',
      render: (f) => (f.valor_de_diferencias === null ? '' : formatearImporteDeReporte(f.valor_de_diferencias)),
    })
  }
  return columnas
}

function columnasDeJornadas(
  zona: string,
  veCostos: boolean,
  abierta: string | undefined,
  alternar: (jornadaId: string) => void,
): ColumnaTabla<JornadaDeRendicion>[] {
  const fecha = (momento: string | null) => (momento === null ? '' : formatearMomento(momento, zona))
  // Sin rendición no hay faltantes ni sobrantes: «Sin conteo» (RUT-07).
  const unidades = (valor: number | null, conConteo: boolean) =>
    !conConteo || valor === null ? 'Sin conteo' : formatearUnidades(valor)
  const columnas: ColumnaTabla<JornadaDeRendicion>[] = [
    { clave: 'vendedor', encabezado: 'Vendedor', render: (f) => f.vendedor_nombre },
    { clave: 'jornada', encabezado: 'Jornada', render: (f) => etiquetaDeEstadoDeJornada(f.estado) },
    { clave: 'ubicacion', encabezado: 'Ubicación', render: (f) => f.ubicacion_nombre },
    { clave: 'abierta', encabezado: 'Abierta', render: (f) => fecha(f.abierta_en) },
    { clave: 'rendida', encabezado: 'Rendida', render: (f) => fecha(f.rendida_en) },
    { clave: 'cerrada', encabezado: 'Cerrada', render: (f) => fecha(f.cerrada_en) },
    { clave: 'liberada', encabezado: 'Liberada', render: (f) => fecha(f.liberada_en) },
    {
      clave: 'ventas',
      encabezado: 'Ventas',
      render: (f) => <CantidadYTotal cantidad={f.ventas.cantidad} total={formatearImporteDeReporte(f.ventas.total)} />,
    },
    {
      clave: 'anuladas',
      encabezado: 'Anuladas',
      render: (f) => <CantidadYTotal cantidad={f.anuladas.cantidad} total={formatearImporteDeReporte(f.anuladas.total)} />,
    },
    { clave: 'cobrado', encabezado: 'Cobrado', render: (f) => <Cobrado cobranzas={f.cobranzas} /> },
    {
      clave: 'despues',
      encabezado: 'Después de la rendición',
      render: (f) => <DespuesDeLaRendicion dinero={f.despues_de_la_rendicion} />,
    },
    { clave: 'faltantes', encabezado: 'Faltantes', render: (f) => unidades(f.faltantes, f.con_conteo) },
    { clave: 'sobrantes', encabezado: 'Sobrantes', render: (f) => unidades(f.sobrantes, f.con_conteo) },
  ]
  if (veCostos) {
    columnas.push({
      clave: 'valor',
      encabezado: 'Valor de las diferencias',
      render: (f) => (f.valor_de_diferencias === null ? '' : formatearImporteDeReporte(f.valor_de_diferencias)),
    })
  }
  columnas.push({
    clave: 'detalle',
    encabezado: '',
    render: (f) => (
      <button
        type="button"
        aria-expanded={abierta === f.jornada_id}
        onClick={() => alternar(f.jornada_id)}
        className="text-sm text-primary/70 underline hover:text-primary"
      >
        Ver detalle
      </button>
    ),
  })
  return columnas
}

/** El resumen de RUT-07 de una jornada, pedido al reporte y mostrado con el componente del detalle de jornadas. */
function DetalleDeLaJornada({ jornada }: { jornada: JornadaDeRendicion }) {
  const detalle = useDetalleDeRendicion(jornada.jornada_id)

  if (detalle.isPending) return <p className="text-sm text-primary/70">Cargando…</p>
  if (detalle.isError) return <Alert>{mensajeDeErrorDeReportes(detalle.error)}</Alert>
  return <ResumenDeJornadaVista datos={detalle.data} contexto={contextoDelDetalle(detalle.data)} />
}

/**
 * Nombres y presentaciones de referencia que el propio reporte trae por línea: quien lee reportes no tiene
 * el permiso del catálogo ni el de stock, así que no se piden `/catalogo/productos` ni los saldos.
 */
function contextoDelDetalle(detalle: ResumenDeJornadaDeReporte): ContextoDelResumen {
  const nombres = new Map<string, string>()
  const referencias = new Map<string, ReferenciaDePresentacion>()
  for (const linea of detalle.lineas) {
    if (linea.producto_nombre !== null) nombres.set(linea.producto_id, linea.producto_nombre)
    const referencia = referenciaDeRespuesta(linea.unidades_referencia, linea.nombre_referencia)
    if (referencia !== null) referencias.set(linea.producto_id, referencia)
  }
  return { nombres, referencias }
}

function Cuerpo({
  reporte,
  alCambiarPagina,
}: {
  reporte: ReporteDeRendiciones
  alCambiarPagina: (pagina: number) => void
}) {
  const [abierta, setAbierta] = useState<string | undefined>(undefined)
  const alternar = (jornadaId: string) => setAbierta((actual) => (actual === jornadaId ? undefined : jornadaId))

  if (reporte.jornadas.total_filas === 0) {
    return <p className="text-sm text-primary/70">Sin jornadas en el período.</p>
  }
  const seleccionada = reporte.jornadas.filas.find((j) => j.jornada_id === abierta)
  return (
    <>
      <Seccion titulo="Por vendedor">
        <div className="overflow-x-auto">
          <Tabla
            etiqueta="Por vendedor"
            filas={reporte.por_vendedor}
            columnas={columnasPorVendedor(reporte.ve_costos)}
            obtenerClave={(f) => f.vendedor_id}
          />
        </div>
      </Seccion>
      <Seccion titulo="Jornadas">
        <div className="overflow-x-auto">
          <Tabla
            etiqueta="Jornadas"
            filas={reporte.jornadas.filas}
            columnas={columnasDeJornadas(reporte.periodo.zona_horaria, reporte.ve_costos, abierta, alternar)}
            obtenerClave={(f) => f.jornada_id}
          />
        </div>
        <Paginacion
          pagina={reporte.jornadas.pagina}
          paginas={reporte.jornadas.paginas}
          alCambiar={alCambiarPagina}
          etiqueta="Jornadas"
        />
      </Seccion>
      {seleccionada !== undefined && <DetalleDeLaJornada jornada={seleccionada} />}
    </>
  )
}

/**
 * Pestaña «Rendiciones» de `/admin/reportes` (change 26, tarea 11.1; D7, D11, D12; RUT-07, ADR-068): la tabla por
 * vendedor, la lista de jornadas abiertas en el período con su estado («En curso» la abierta), «Sin conteo»
 * donde no hubo rendición, lo registrado después de la rendición aparte y «Ver detalle», que abre el resumen de
 * la jornada con el mismo componente del detalle de jornadas. Sin `VER_COSTOS` el servidor manda el valor de las
 * diferencias en `null` y la columna no se muestra. Todo sale del servidor: la pantalla no calcula nada.
 */
export function RendicionesReporte() {
  const [filtros, setFiltros] = useState<FiltrosDeRendiciones>({})
  // Cambiar el período, el vendedor o el estado vuelve a la página 1 (D14).
  const [{ pagina }, irAPagina] = usePaginas(JSON.stringify(filtros), { pagina: 1 })
  const reporte = useReporteDeRendiciones({ ...filtros, pagina })
  const datos = reporte.data
  const vendedores = useVendedoresVistos(datos, (d) =>
    d.por_vendedor.map((v) => ({ id: v.vendedor_id, nombre: v.vendedor_nombre })),
  )

  return (
    <div className="flex flex-col gap-4">
      <TituloDePestana titulo="Rendiciones" ayuda="reportes.rendiciones" />
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
          <Rotulo id="filtro-estado" etiqueta="Estado">
            <select
              id="filtro-estado"
              className={CLASE_CONTROL}
              value={filtros.estado ?? ''}
              onChange={(e) =>
                setFiltros((actual) => ({ ...actual, estado: (e.target.value || undefined) as EstadoDeJornadaFiltro | undefined }))
              }
            >
              <option value="">Todos</option>
              {ESTADOS.map((estado) => (
                <option key={estado} value={estado}>
                  {etiquetaDeEstadoDeJornada(estado)}
                </option>
              ))}
            </select>
          </Rotulo>
        </div>
      </Card>

      <EstadoDelReporte cargando={reporte.isPending} error={reporte.error} />
      {datos !== undefined && !reporte.isError && (
        <Cuerpo reporte={datos} alCambiarPagina={(nueva) => irAPagina('pagina', nueva)} />
      )}
    </div>
  )
}

export default RendicionesReporte
