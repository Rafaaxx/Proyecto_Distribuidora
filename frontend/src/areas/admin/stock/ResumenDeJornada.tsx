import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Card } from '../../../components/ui/Card'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { formatearCantidad, referenciaDeRespuesta, type ReferenciaDePresentacion } from '../../../domain/stock/cantidades'
import { usePermisos } from '../../../features/identidad/usePermisos'
import type { DineroDeLaJornada, LineaDelResumen } from '../../../features/stock/api'
import { useProductosParaRendicion, useResumenDeJornada, useSaldosCompletos } from '../../../features/stock/hooks'
import { formatearImporte, parsearImporteDesdeApi } from '../../../lib/money'

/**
 * Resumen de una jornada en `/admin` (change 24, tarea 13.1; `design.md` D4, D8, D9; RUT-07, STK-04,
 * INV-03): el stock por producto (al abrir, ingresos, ventas, anulaciones, otros, esperado y, si
 * hubo conteo, contado y diferencia), el dinero (ventas, anuladas, cobranzas por medio de pago) y lo
 * que llegó después de la rendición, aparte. Todo lo calcula el servidor con SQL: acá solo se
 * muestra (los importes llegan como string y se formatean sin `number`). El valor de las
 * diferencias solo viaja con `VER_COSTOS`.
 */
export interface ResumenDeJornadaProps {
  jornadaId: string
  /** Ubicación de la jornada: de sus saldos salen las presentaciones para mostrar cajas y unidades. */
  ubicacionId: string
}

const dinero = (valor: string) => formatearImporte(parsearImporteDesdeApi(valor))

export function ResumenDeJornada({ jornadaId, ubicacionId }: ResumenDeJornadaProps) {
  const resumen = useResumenDeJornada(jornadaId)
  const catalogo = useProductosParaRendicion()
  const permisos = usePermisos()
  const saldos = useSaldosCompletos(permisos.tiene('TRANSFERIR_STOCK') ? ubicacionId : undefined)

  if (resumen.isPending) return <p className="text-sm text-primary/70">Cargando…</p>
  if (resumen.isError) return <Alert>No se pudo obtener el resumen de la jornada.</Alert>

  const datos = resumen.data
  const nombres = new Map(catalogo.productos.map((p) => [p.id, p.nombre]))
  const referencias = new Map<string, ReferenciaDePresentacion>()
  for (const saldo of saldos.lineas) {
    const referencia = referenciaDeRespuesta(saldo.unidades_referencia, saldo.nombre_referencia)
    if (referencia !== null) referencias.set(saldo.producto_id, referencia)
  }
  const cantidad = (productoId: string, valor: number) => formatearCantidad(valor, referencias.get(productoId) ?? null)
  const conValor = datos.valor_de_diferencias !== undefined && datos.valor_de_diferencias !== null

  const numerica = (clave: keyof Pick<LineaDelResumen, 'al_abrir' | 'ingresos' | 'ventas' | 'anulaciones' | 'otros' | 'esperado'>, encabezado: string): ColumnaTabla<LineaDelResumen> => ({
    clave,
    encabezado,
    render: (fila) => cantidad(fila.producto_id, fila[clave]),
  })
  const columnas: ColumnaTabla<LineaDelResumen>[] = [
    {
      clave: 'producto',
      encabezado: 'Producto',
      render: (fila) => <span className="font-medium">{nombres.get(fila.producto_id) ?? `Producto ${fila.producto_id.slice(0, 8)}`}</span>,
    },
    numerica('al_abrir', 'Al abrir'),
    numerica('ingresos', 'Ingresos'),
    numerica('ventas', 'Ventas'),
    numerica('anulaciones', 'Anulaciones'),
    numerica('otros', 'Otros'),
    numerica('esperado', 'Esperado'),
    ...(datos.con_conteo
      ? [
          {
            clave: 'contado',
            encabezado: 'Contado',
            render: (fila: LineaDelResumen) => (fila.contado === null ? '—' : cantidad(fila.producto_id, fila.contado)),
          },
          {
            clave: 'diferencia',
            encabezado: 'Diferencia',
            render: (fila: LineaDelResumen) =>
              fila.diferencia === null ? (
                '—'
              ) : (
                <span className={fila.diferencia < 0 ? 'font-medium text-danger' : undefined}>{cantidad(fila.producto_id, fila.diferencia)}</span>
              ),
          },
        ]
      : []),
    ...(conValor
      ? [
          {
            clave: 'valor',
            encabezado: 'Valor de la diferencia',
            render: (fila: LineaDelResumen) =>
              fila.valor_diferencia === undefined || fila.valor_diferencia === null ? '—' : dinero(fila.valor_diferencia),
          },
        ]
      : []),
  ]

  const hayTardios = datos.despues_de_la_rendicion !== null && hayMovimiento(datos.despues_de_la_rendicion)

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-center gap-1">
        <h2 className="text-base font-semibold text-primary">Resumen de la jornada</h2>
        <Ayuda clave="stock.resumenJornada" />
      </div>

      {!datos.con_conteo && datos.estado !== 'ABIERTA' && <p className="text-sm text-primary/70">Esta jornada no tiene conteo.</p>}

      <div className="overflow-x-auto">
        <Tabla filas={datos.lineas} columnas={columnas} obtenerClave={(fila) => fila.producto_id} etiqueta="Stock de la jornada" />
      </div>
      {conValor && datos.valor_de_diferencias != null && (
        <p className="text-sm font-medium text-primary">Valor de la diferencia: {dinero(datos.valor_de_diferencias)}</p>
      )}

      <DineroDeLaJornadaVista dinero={datos.dinero} />

      {hayTardios && datos.despues_de_la_rendicion !== null && (
        <section className="flex flex-col gap-2 border-t border-border pt-3">
          <h3 className="text-sm font-semibold text-primary">Llegaron después de la rendición</h3>
          <DineroDeLaJornadaVista dinero={datos.despues_de_la_rendicion} />
        </section>
      )}
    </Card>
  )
}

function hayMovimiento(d: DineroDeLaJornada): boolean {
  return d.ventas.cantidad + d.anuladas.cantidad + d.cobranzas.cantidad + d.cobranzas_anuladas.cantidad > 0
}

/** Ventas, anuladas, cobranzas por medio de pago y cobranzas anuladas (importes tal como vienen, INV-03). */
function DineroDeLaJornadaVista({ dinero: d }: { dinero: DineroDeLaJornada }) {
  return (
    <div className="flex flex-col gap-3 text-sm text-primary">
      <p>
        Ventas: {d.ventas.cantidad} por {dinero(d.ventas.total)}
      </p>
      <p>
        Anuladas: {d.anuladas.cantidad} por {dinero(d.anuladas.total)}
      </p>
      <section className="flex flex-col gap-1">
        <h3 className="font-semibold">Cobranzas por medio de pago</h3>
        <ListaPorMedio cobranzas={d.cobranzas} />
      </section>
      <section className="flex flex-col gap-1">
        <h3 className="font-semibold">Cobranzas anuladas</h3>
        <ListaPorMedio cobranzas={d.cobranzas_anuladas} />
      </section>
    </div>
  )
}

function ListaPorMedio({ cobranzas }: { cobranzas: DineroDeLaJornada['cobranzas'] }) {
  if (cobranzas.por_medio.length === 0) return <p className="text-primary/70">Sin cobranzas.</p>
  return (
    <ul className="flex flex-col gap-0.5">
      {cobranzas.por_medio.map((medio) => (
        <li key={medio.medio_pago_id}>
          {medio.nombre ?? medio.medio_pago_id}: {dinero(medio.total)}
        </li>
      ))}
    </ul>
  )
}
