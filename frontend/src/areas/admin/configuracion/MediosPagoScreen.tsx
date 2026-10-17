import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import type { MedioPagoAdmin } from '../../../features/configuracion/api'
import { useMediosPagoAdmin } from '../../../features/configuracion/useMediosPagoAdmin'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { CambioDeEstadoDeMedioDialogo } from './CambioDeEstadoDeMedioDialogo'
import { MedioPagoDialogo } from './MedioPagoDialogo'

const TITULO = 'Medios de pago'

type Accion = { tipo: 'nuevo' } | { tipo: 'editar' | 'baja' | 'reactivar'; medio: MedioPagoAdmin }

function SinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} />
      <p className="text-sm text-primary/70">No tenés permiso para administrar los medios de pago.</p>
    </main>
  )
}

/**
 * Medios de pago de la organización (change 17b, tarea 8.1; spec `administracion-de-medios-de-pago`;
 * TR-09, CAT-05, ADR-053). Lista activos e inactivos; alta, edición, baja y reactivación con
 * `ADMIN_CONFIGURACION` (ADR-027: sin el permiso la pantalla no se monta ni pide nada). Nunca se
 * borra un medio. Sin lógica de negocio: las reglas las valida el servidor.
 */
export function MediosPagoScreen() {
  return (
    <SiTienePermiso permiso="ADMIN_CONFIGURACION" fallback={<SinPermiso />}>
      <MediosPagoListado />
    </SiTienePermiso>
  )
}

function MediosPagoListado() {
  const medios = useMediosPagoAdmin()
  const [accion, setAccion] = useState<Accion | null>(null)
  const cerrar = () => setAccion(null)

  const columnas: ColumnaTabla<MedioPagoAdmin>[] = [
    { clave: 'nombre', encabezado: 'Nombre', render: (m) => <span className="font-medium text-primary">{m.nombre}</span> },
    {
      clave: 'referencia',
      encabezado: 'Pide referencia',
      ayuda: 'mediosPago.requiereReferencia',
      render: (m) => (m.requiere_referencia ? 'Sí' : 'No'),
    },
    {
      clave: 'estado',
      encabezado: 'Estado',
      render: (m) => <Badge variante={m.activo ? 'positivo' : 'negativo'}>{m.activo ? 'Activo' : 'De baja'}</Badge>,
    },
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      ayuda: 'mediosPago.baja',
      render: (m) => (
        <span className="flex items-center gap-2">
          <Boton variante="secundario" aria-label={`Editar ${m.nombre}`} onClick={() => setAccion({ tipo: 'editar', medio: m })}>
            Editar
          </Boton>
          {m.activo ? (
            <Boton variante="secundario" aria-label={`Dar de baja ${m.nombre}`} onClick={() => setAccion({ tipo: 'baja', medio: m })}>
              Dar de baja
            </Boton>
          ) : (
            <Boton variante="secundario" aria-label={`Reactivar ${m.nombre}`} onClick={() => setAccion({ tipo: 'reactivar', medio: m })}>
              Reactivar
            </Boton>
          )}
        </span>
      ),
    },
  ]

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} acciones={<Boton onClick={() => setAccion({ tipo: 'nuevo' })}>Nuevo medio de pago</Boton>} />
      <p className="text-sm text-primary/70">
        Son las formas en que te pagan o pagás. Un medio dado de baja no se borra: los cobros y pagos de antes lo siguen mostrando.
      </p>
      {medios.isPending && <p>Cargando…</p>}
      {medios.isError && <Alert>No se pudieron obtener los medios de pago.</Alert>}
      {medios.isSuccess && medios.data.length === 0 && <p className="text-sm text-primary/70">Todavía no hay medios de pago.</p>}
      {medios.isSuccess && medios.data.length > 0 && (
        <Card>
          <Tabla filas={medios.data} columnas={columnas} obtenerClave={(m) => m.id} etiqueta={TITULO} />
        </Card>
      )}
      {accion?.tipo === 'nuevo' && <MedioPagoDialogo onCerrar={cerrar} />}
      {accion?.tipo === 'editar' && <MedioPagoDialogo key={accion.medio.id} medio={accion.medio} onCerrar={cerrar} />}
      {(accion?.tipo === 'baja' || accion?.tipo === 'reactivar') && (
        <CambioDeEstadoDeMedioDialogo
          key={accion.medio.id}
          medio={accion.medio}
          reactivar={accion.tipo === 'reactivar'}
          onCerrar={cerrar}
        />
      )}
    </main>
  )
}

export default MediosPagoScreen
