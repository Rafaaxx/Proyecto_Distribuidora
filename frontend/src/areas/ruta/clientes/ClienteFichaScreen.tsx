import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Badge } from '../../../components/ui/Badge'
import { Card } from '../../../components/ui/Card'
import { disponibleDeCredito, formatearDinero } from '../../../domain/ruta/lecturasLocales'
import { formatearFechaHora } from '../../../lib/fecha'
import { useClienteLocal, useDatosDeInicio } from '../datos/lecturas'
import { useSesionRutaActiva } from '../sesion/contextoSesion'

/**
 * Ficha de un cliente en `/ruta` (change 21, `design.md` D19; CRE-01, INV-03). Saldo y crédito
 * son los del bootstrap, con su fecha: no se recalculan. Disponible = límite - saldo con el
 * motor decimal compartido.
 */
function Fila({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <div className="flex flex-col">
      <dt className="text-xs text-primary/70">{rotulo}</dt>
      <dd className="text-sm text-primary">{children}</dd>
    </div>
  )
}

export function ClienteFichaScreen() {
  const { id = '' } = useParams()
  const datos = useClienteLocal(id)
  const inicio = useDatosDeInicio()
  const { entrada } = useSesionRutaActiva()
  // D14: "Vender" solo con VENDER en el bootstrap, jornada abierta y datos del día.
  const puedeVender = inicio.estado === 'listo' && inicio.permisos.includes('VENDER') && entrada.tipo !== 'sin_jornada'

  if (datos.estado === 'cargando') return <p className="text-sm text-primary">Cargando…</p>
  if (datos.estado === 'sin_datos') {
    return <p className="text-sm text-primary">Todavía no hay datos descargados. Abrí una jornada desde el inicio.</p>
  }
  if (datos.cliente === null) {
    return (
      <div className="flex flex-col gap-3">
        <h1 className="text-lg font-semibold text-primary">No encontramos ese cliente</h1>
        <Link to="/ruta/clientes" className="text-sm underline">
          Volver a Clientes
        </Link>
      </div>
    )
  }

  const { cliente } = datos
  const disponible = disponibleDeCredito(cliente.credito.limite, cliente.saldo)

  return (
    <div className="flex flex-col gap-3">
      <Link to="/ruta/clientes" className="text-sm underline">
        Volver a Clientes
      </Link>
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-lg font-semibold text-primary">{cliente.nombre}</h1>
        {cliente.estado === 'SUSPENDIDO' && <Badge variante="negativo">Suspendido</Badge>}
        {cliente.es_consumidor_final && <Badge>Consumidor final</Badge>}
      </div>
      <p className="text-xs text-primary/70">Datos de {formatearFechaHora(datos.fechaBootstrap).trim()}</p>

      <Card>
        <dl className="flex flex-col gap-3">
          {cliente.razon_social && <Fila rotulo="Razón social">{cliente.razon_social}</Fila>}
          {cliente.documento_numero && (
            <Fila rotulo="Documento">{`${cliente.documento_tipo ?? ''} ${cliente.documento_numero}`.trim()}</Fila>
          )}
          <Fila rotulo="Dirección">{cliente.direccion}</Fila>
          {cliente.telefono && <Fila rotulo="Teléfono">{cliente.telefono}</Fila>}
          {datos.listaNombre && <Fila rotulo="Lista de precios">{datos.listaNombre}</Fila>}
        </dl>
      </Card>

      {puedeVender && (
        <Link
          to={`/ruta/vender?cliente=${cliente.id}`}
          className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-3 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          Vender
        </Link>
      )}

      <Card>
        <dl className="flex flex-col gap-3">
          <Fila rotulo="Saldo">{formatearDinero(cliente.saldo)}</Fila>
          <Fila rotulo="Límite de crédito">
            {cliente.credito.limite === null ? 'Sin límite' : formatearDinero(cliente.credito.limite)}
          </Fila>
          <Fila rotulo="Disponible">{disponible === null ? 'Sin límite' : formatearDinero(disponible)}</Fila>
        </dl>
      </Card>
    </div>
  )
}

export default ClienteFichaScreen
