import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import {
  AMBITOS_DE_MOTIVO,
  NOMBRE_DE_AMBITO,
  type AmbitoDeMotivo,
} from '../../../domain/configuracion/catalogos'
import type { MotivoAdmin } from '../../../features/configuracion/api'
import { useModificarMotivo, useMotivosAdmin } from '../../../features/configuracion/useMotivosAdmin'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { CambioDeEstadoDeCatalogoDialogo } from './CambioDeEstadoDeCatalogoDialogo'
import { describirErrorDeMotivo } from './erroresDeCatalogos'
import { MotivoDialogo } from './MotivoDialogo'

const TITULO = 'Motivos'
const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

type Accion = { tipo: 'nuevo' } | { tipo: 'editar' | 'baja' | 'reactivar'; motivo: MotivoAdmin }

function SinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} />
      <p className="text-sm text-primary/70">No tenés permiso para administrar los motivos.</p>
    </main>
  )
}

/**
 * Motivos de la organización por ámbito (change 20c, tarea 7.2; spec `administracion-de-motivos`;
 * TR-09, CAT-05, ADR-061). Lista activos e inactivos del ámbito elegido; alta, cambio de nombre,
 * baja y reactivación con `ADMIN_CONFIGURACION` (ADR-027: sin el permiso la pantalla no se monta ni
 * pide nada). Nunca se borra un motivo. Sin lógica de negocio: las reglas las valida el servidor.
 */
export function MotivosScreen() {
  return (
    <SiTienePermiso permiso="ADMIN_CONFIGURACION" fallback={<SinPermiso />}>
      <MotivosListado />
    </SiTienePermiso>
  )
}

function MotivosListado() {
  const [ambito, setAmbito] = useState<AmbitoDeMotivo>('AJUSTE_STOCK')
  const motivos = useMotivosAdmin(ambito)
  const modificar = useModificarMotivo()
  const [accion, setAccion] = useState<Accion | null>(null)
  const cerrar = () => setAccion(null)

  const columnas: ColumnaTabla<MotivoAdmin>[] = [
    { clave: 'nombre', encabezado: 'Nombre', render: (m) => <span className="font-medium text-primary">{m.nombre}</span> },
    {
      clave: 'estado',
      encabezado: 'Estado',
      render: (m) => <Badge variante={m.activo ? 'positivo' : 'negativo'}>{m.activo ? 'Activo' : 'De baja'}</Badge>,
    },
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      ayuda: 'motivos.baja',
      render: (m) => (
        <span className="flex items-center gap-2">
          <Boton variante="secundario" aria-label={`Editar ${m.nombre}`} onClick={() => setAccion({ tipo: 'editar', motivo: m })}>
            Editar
          </Boton>
          {m.activo ? (
            <Boton variante="secundario" aria-label={`Dar de baja ${m.nombre}`} onClick={() => setAccion({ tipo: 'baja', motivo: m })}>
              Dar de baja
            </Boton>
          ) : (
            <Boton variante="secundario" aria-label={`Reactivar ${m.nombre}`} onClick={() => setAccion({ tipo: 'reactivar', motivo: m })}>
              Reactivar
            </Boton>
          )}
        </span>
      ),
    },
  ]

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} acciones={<Boton onClick={() => setAccion({ tipo: 'nuevo' })}>Nuevo motivo</Boton>} />
      <p className="text-sm text-primary/70">
        Son las razones que se eligen al ajustar stock, anular una operación o dar un descuento. Un motivo dado de baja no se
        borra: las operaciones de antes lo siguen mostrando.
      </p>
      <Campo id="motivos-ambito" etiqueta="Ámbito" ayuda="motivos.ambito">
        <select
          id="motivos-ambito"
          className={`${CLASE_CONTROL} max-w-xs`}
          value={ambito}
          onChange={(evento) => setAmbito(evento.target.value as AmbitoDeMotivo)}
        >
          {AMBITOS_DE_MOTIVO.map((codigo) => (
            <option key={codigo} value={codigo}>
              {NOMBRE_DE_AMBITO[codigo]}
            </option>
          ))}
        </select>
      </Campo>
      {motivos.isPending && <p>Cargando…</p>}
      {motivos.isError && <Alert>No se pudieron obtener los motivos.</Alert>}
      {motivos.isSuccess && motivos.data.length === 0 && (
        <p className="text-sm text-primary/70">Este ámbito todavía no tiene motivos.</p>
      )}
      {motivos.isSuccess && motivos.data.length > 0 && (
        <Card>
          <Tabla filas={motivos.data} columnas={columnas} obtenerClave={(m) => m.id} etiqueta={TITULO} />
        </Card>
      )}
      {accion?.tipo === 'nuevo' && <MotivoDialogo ambito={ambito} onCerrar={cerrar} />}
      {accion?.tipo === 'editar' && <MotivoDialogo key={accion.motivo.id} ambito={ambito} motivo={accion.motivo} onCerrar={cerrar} />}
      {(accion?.tipo === 'baja' || accion?.tipo === 'reactivar') && (
        <CambioDeEstadoDeCatalogoDialogo
          key={accion.motivo.id}
          id={accion.motivo.id}
          titulo={`${accion.tipo === 'reactivar' ? 'Reactivar' : 'Dar de baja'} ${accion.motivo.nombre}`}
          mensaje={
            accion.tipo === 'reactivar'
              ? `«${accion.motivo.nombre}» vuelve a ofrecerse en las operaciones nuevas.`
              : `«${accion.motivo.nombre}» deja de ofrecerse en las operaciones nuevas. No se borra: las de antes lo siguen mostrando y lo podés reactivar cuando quieras.`
          }
          reactivar={accion.tipo === 'reactivar'}
          describirError={describirErrorDeMotivo}
          onConfirmar={(operationId) =>
            modificar.mutateAsync({
              motivoId: accion.motivo.id,
              nombre: accion.motivo.nombre,
              activo: accion.tipo === 'reactivar',
              operationId,
            })
          }
          onCerrar={cerrar}
        />
      )}
    </main>
  )
}

export default MotivosScreen
