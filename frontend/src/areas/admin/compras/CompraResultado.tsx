import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { construirCostoInformar, type FormularioDeCompra } from '../../../domain/compras/formularioCompra'
import type { CompraConfirmarResultado, DiferenciaDeCosto } from '../../../features/compras/api'
import { useOperationIdPorContenido } from '../../../features/compras/useOperationIdPorContenido'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { ErrorDeProveedores } from '../../../features/proveedores/errores'
import { useInformarCostos } from '../../../features/proveedores/useMutaciones'
import { formatearCosto, formatearImporte, parsearImporteDesdeApi } from '../../../lib/money'

/**
 * Resultado de una compra confirmada (change 11, tarea 12.2; spec
 * `administracion-de-compras`, CMP-04, `design.md` D7). Muestra la compra registrada y,
 * por cada línea cuyo costo difiere del vigente, ofrece "Registrar como costo informado"
 * solo con `EDITAR_COSTOS`. Nada se registra sin esa acción.
 */

interface Props {
  resultado: CompraConfirmarResultado
  /** CST-06: la regla con la que se registró la compra (el costo a informar la respeta). */
  computaCreditoFiscal: boolean
  /** El formulario tal como se envió: de ahí salen presentación, valor, IVA y bonificación. */
  formulario: FormularioDeCompra
  nombresDeProductos: Readonly<Record<string, string>>
}

export function CompraResultado({ resultado, computaCreditoFiscal, formulario, nombresDeProductos }: Props) {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Compra registrada" />
      <Card className="flex flex-col gap-1 text-sm text-primary">
        <p>
          Total neto: <span data-testid="resultado-total-neto">{formatearImporte(parsearImporteDesdeApi(resultado.total_neto))}</span>
        </p>
        <p>
          Total de factura:{' '}
          <span data-testid="resultado-total-factura">{formatearImporte(parsearImporteDesdeApi(resultado.total_factura))}</span>
        </p>
      </Card>

      {resultado.diferencias_de_costo.length > 0 && (
        <SiTienePermiso permiso="EDITAR_COSTOS">
          <Card className="flex flex-col gap-3">
            <h2 className="text-base font-semibold text-primary">Costos distintos del vigente</h2>
            <p className="text-sm text-primary/70">
              No se registra ningún costo informado salvo que lo pidas en cada línea.
            </p>
            {resultado.diferencias_de_costo.map((diferencia) => (
              <OfertaDeCosto
                key={diferencia.linea}
                diferencia={diferencia}
                formulario={formulario}
                computaCreditoFiscal={computaCreditoFiscal}
                nombre={nombresDeProductos[diferencia.producto_id] ?? 'Producto'}
              />
            ))}
          </Card>
        </SiTienePermiso>
      )}

      <div className="flex gap-3 text-sm">
        <Link to={`/admin/compras/${resultado.compra_id}`} className="text-primary hover:underline">
          Ver compra
        </Link>
        <Link to="/admin/compras/nueva" reloadDocument className="text-primary/70 hover:text-primary hover:underline">
          Nueva compra
        </Link>
        <Link to="/admin/compras" className="text-primary/70 hover:text-primary hover:underline">
          Volver al listado
        </Link>
      </div>
    </main>
  )
}

function OfertaDeCosto({
  diferencia,
  formulario,
  computaCreditoFiscal,
  nombre,
}: {
  diferencia: DiferenciaDeCosto
  formulario: FormularioDeCompra
  computaCreditoFiscal: boolean
  nombre: string
}) {
  const informar = useInformarCostos()
  const [registrado, setRegistrado] = useState(false)
  const linea = formulario.lineas[diferencia.linea]
  const costo = linea ? construirCostoInformar(linea, formulario.fecha, computaCreditoFiscal) : null
  const operationId = useOperationIdPorContenido(costo)

  const alRegistrar = async () => {
    if (!costo) return
    try {
      await informar.mutateAsync({ proveedor_id: formulario.proveedorId, costos: [costo], operationId })
      setRegistrado(true)
    } catch {
      // El error queda en `informar.error` y se muestra abajo.
    }
  }

  const vigente = diferencia.costo_base_vigente
  const mensajeDeError =
    informar.error instanceof ErrorDeProveedores ? informar.error.message : informar.error ? 'No se pudo registrar el costo.' : null

  return (
    <div className="flex flex-col gap-1 border-t border-border pt-2 text-sm">
      <p className="font-medium text-primary">{nombre}</p>
      <p className="text-primary/70">
        Costo de la compra: {formatearCosto(parsearImporteDesdeApi(diferencia.costo_base_compra))} — vigente:{' '}
        {vigente === null ? 'sin costo vigente' : formatearCosto(parsearImporteDesdeApi(vigente))}
      </p>
      {registrado ? (
        <p className="text-primary">Costo informado registrado.</p>
      ) : (
        <Boton
          variante="secundario"
          className="self-start"
          disabled={informar.isPending || costo === null}
          onClick={() => void alRegistrar()}
        >
          Registrar como costo informado
        </Boton>
      )}
      {mensajeDeError && !registrado && <Alert>{mensajeDeError}</Alert>}
    </div>
  )
}
