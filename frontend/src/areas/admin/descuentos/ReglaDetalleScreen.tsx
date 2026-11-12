import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import {
  accionesDeRegla,
  describirRegla,
  describirVigencia,
  etiquetaDeEstadoDeRegla,
} from '../../../domain/descuentos/presentacion'
import { ErrorDeApiDescuentos, PermisoRequeridoDescuentosError } from '../../../features/descuentos/errores'
import { useReglaDescuento } from '../../../features/descuentos/hooks'
import { usePermisos } from '../../../features/identidad/usePermisos'
import { CambioDeEstadoDialogo, type TipoDeCambio } from './CambioDeEstadoDialogo'
import { DescuentosSinPermiso } from './DescuentosSinPermiso'
import { PonerFinDialogo } from './PonerFinDialogo'

const TITULO = 'Regla de descuento'
const ENLACE = 'text-sm text-primary/70 hover:text-primary hover:underline'

type Dialogo = TipoDeCambio | 'FIN' | null

function varianteDeEstado(estado: string) {
  return estado === 'ACTIVA' ? 'positivo' : estado === 'VENCIDA' ? 'negativo' : 'neutral'
}

/**
 * Detalle de una regla de descuento en `/admin/descuentos/:reglaId` (change 16, tarea 15.3; spec
 * `administracion-de-descuentos`, `01` §18). "Activar" (borrador o pausada) y "Pausar" (activa)
 * piden confirmación; una regla activada es de solo lectura salvo "Poner fin", que fija su
 * vigencia hasta (D15). Qué se ofrece lo decide `accionesDeRegla`; el servidor valida igual.
 */
export function ReglaDetalleScreen() {
  const { reglaId } = useParams<{ reglaId: string }>()
  const regla = useReglaDescuento(reglaId)
  const permisos = usePermisos()
  const [dialogo, setDialogo] = useState<Dialogo>(null)
  const [aviso, setAviso] = useState<string | null>(null)

  if (regla.isPending) {
    return (
      <main>
        <p>Cargando…</p>
      </main>
    )
  }
  if (regla.isError) {
    if (regla.error instanceof PermisoRequeridoDescuentosError) return <DescuentosSinPermiso titulo={TITULO} />
    const noExiste = regla.error instanceof ErrorDeApiDescuentos && regla.error.estado === 404
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo={TITULO} />
        <Alert>{noExiste ? 'No se encontró la regla.' : 'No se pudo obtener la regla.'}</Alert>
      </main>
    )
  }

  const detalle = regla.data
  const descripcion = describirRegla(detalle)
  const acciones = accionesDeRegla(detalle.estado, permisos.yo?.permisos ?? [])
  const soloLectura = detalle.estado !== 'BORRADOR'

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo={detalle.nombre}
        acciones={
          <>
            {acciones.editar && (
              <Link to={`/admin/descuentos/${detalle.id}/editar`} className={ENLACE}>
                Editar
              </Link>
            )}
            {acciones.activar && (
              <span className="inline-flex items-center gap-1">
                <Boton onClick={() => setDialogo('ACTIVAR')}>Activar</Boton>
                <Ayuda clave="descuentos.activar" />
              </span>
            )}
            {acciones.pausar && (
              <Boton variante="secundario" onClick={() => setDialogo('PAUSAR')}>
                Pausar
              </Boton>
            )}
            {acciones.ponerFin && (
              <Boton variante="secundario" onClick={() => setDialogo('FIN')}>
                Poner fin
              </Boton>
            )}
            <Link to="/admin/descuentos" className={ENLACE}>
              Volver
            </Link>
          </>
        }
      />
      {aviso && <Alert>{aviso}</Alert>}
      <Card>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <dt className="text-primary/70">Regla</dt>
          <dd>{descripcion.resumen}</dd>
          <dt className="text-primary/70">Se aplica a</dt>
          <dd>{descripcion.alcance}</dd>
          <dt className="text-primary/70">Orden</dt>
          <dd>{descripcion.prioridad}</dd>
          <dt className="text-primary/70">Combinación</dt>
          <dd>{descripcion.acumulable}</dd>
          <dt className="text-primary/70">Vigencia</dt>
          <dd>{describirVigencia(detalle.vigencia_desde, detalle.vigencia_hasta)}</dd>
          <dt className="text-primary/70">Estado</dt>
          <dd>
            <Badge variante={varianteDeEstado(detalle.estado)}>{etiquetaDeEstadoDeRegla(detalle.estado)}</Badge>
          </dd>
        </dl>
      </Card>
      {soloLectura && (
        <p className="text-sm text-primary/70">
          Esta regla ya no se edita. Para cambiar su condición, acción, alcance o prioridad hay que pausarla y crear otra;
          lo único que se puede cambiar es su vigencia hasta.
        </p>
      )}

      {(dialogo === 'ACTIVAR' || dialogo === 'PAUSAR') && (
        <CambioDeEstadoDialogo
          tipo={dialogo}
          reglaId={detalle.id}
          nombre={detalle.nombre}
          onCerrar={() => setDialogo(null)}
          onEstadoInvalido={(mensaje) => {
            setDialogo(null)
            setAviso(mensaje)
            void regla.refetch()
          }}
          onHecho={() => {
            setDialogo(null)
            setAviso(null)
          }}
        />
      )}
      {dialogo === 'FIN' && (
        <PonerFinDialogo
          reglaId={detalle.id}
          vigenciaDesde={detalle.vigencia_desde}
          onCerrar={() => setDialogo(null)}
          onEstadoInvalido={(mensaje) => {
            setDialogo(null)
            setAviso(mensaje)
            void regla.refetch()
          }}
          onHecho={() => {
            setDialogo(null)
            setAviso(null)
          }}
        />
      )}
    </main>
  )
}

export default ReglaDetalleScreen
