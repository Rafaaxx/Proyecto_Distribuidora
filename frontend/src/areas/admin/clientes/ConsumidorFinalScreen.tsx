import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import {
  esquemaConsumidorFinalConfigurar,
  type DatosConsumidorFinalConfigurar,
} from '../../../domain/clientes/clienteSchema'
import { ErrorDeClientes } from '../../../features/clientes/errores'
import { useConsumidorFinal } from '../../../features/clientes/useListados'
import { esErrorDeRed, useConfigurarConsumidorFinal } from '../../../features/clientes/useMutaciones'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'

const SIN_PERMISO_DE_CONFIGURACION = 'No tenés permiso para configurar la organización.'
const AVISO_SIN_CONEXION = 'Se necesita conexión para completar esta operación. Probá de nuevo cuando tengas conexión.'

function ConsumidorFinalSinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Consumidor final" />
      <p className="text-sm text-primary/70">{SIN_PERMISO_DE_CONFIGURACION}</p>
    </main>
  )
}

function mensajeDeError(error: unknown): string {
  if (esErrorDeRed(error)) {
    return AVISO_SIN_CONEXION
  }
  if (error instanceof ErrorDeClientes) {
    return error.message
  }
  return 'No se pudo completar la operación.'
}

/**
 * Habilitación del consumidor final (change 07, grupo 5, tarea 5.5;
 * `design.md` D4, ADR-029, D9 enmienda 2026-09-29). Solo el rol con
 * `ADMIN_CONFIGURACION` puede habilitarlo (con las plantillas de rol
 * vigentes, solo Administrador) -- decidido **solo** con la consulta de
 * sesión `['yo']` (ADR-027), el formulario no se monta sin el permiso.
 */
export function ConsumidorFinalScreen() {
  return (
    <SiTienePermiso permiso="ADMIN_CONFIGURACION" fallback={<ConsumidorFinalSinPermiso />}>
      <ConsumidorFinalContenido />
    </SiTienePermiso>
  )
}

function ConsumidorFinalContenido() {
  const consumidorFinal = useConsumidorFinal()
  const configurar = useConfigurarConsumidorFinal()

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<DatosConsumidorFinalConfigurar>({
    resolver: zodResolver(esquemaConsumidorFinalConfigurar),
    defaultValues: { nombre: 'Consumidor final' },
  })

  const alEnviar = handleSubmit(async (datos) => {
    try {
      await configurar.mutateAsync(datos)
    } catch (error) {
      setError('root', { message: mensajeDeError(error) })
    }
  })

  if (consumidorFinal.isPending) {
    return (
      <main>
        <p>Cargando…</p>
      </main>
    )
  }

  if (consumidorFinal.isError) {
    return (
      <main>
        <p role="alert">No se pudo obtener la configuración del consumidor final.</p>
      </main>
    )
  }

  if (consumidorFinal.data.habilitado && consumidorFinal.data.cliente) {
    const cliente = consumidorFinal.data.cliente
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo="Consumidor final" />
        <Card>
          <div className="flex flex-col gap-2">
            <p className="text-sm text-primary/80">
              El consumidor final ya está habilitado (CLI-03): es solo contado, con límite de crédito cero y sin
              política ni tolerancia propias.
            </p>
            <p className="flex items-center gap-2 text-sm">
              <strong>{cliente.nombre}</strong>
              <Badge variante="neutral">Límite {cliente.limite_credito}</Badge>
            </p>
            <Link to={`/admin/clientes/${cliente.id}`} className="text-sm text-primary/70 hover:text-primary hover:underline">
              Ver ficha
            </Link>
          </div>
        </Card>
      </main>
    )
  }

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Consumidor final" />
      <Card>
        <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
          <p className="text-sm text-primary/70">
            Esta organización todavía no habilitó el consumidor final. Al habilitarlo se crea un cliente genérico,
            activo, con límite de crédito cero (CLI-03) -- no se puede deshacer, solo deshabilitar la función más
            adelante desde la ficha del cliente.
          </p>
          <Campo id="nombre" etiqueta="Nombre del cliente genérico" error={errors.nombre?.message}>
            <input id="nombre" className="rounded-md border border-border px-2 py-1 text-sm" {...register('nombre')} />
          </Campo>

          {errors.root?.message && <Alert>{errors.root.message}</Alert>}

          <div className="flex gap-2">
            <Boton type="submit" disabled={configurar.isPending}>
              Habilitar consumidor final
            </Boton>
            <Link to="/admin/clientes" className="text-sm text-primary/70 hover:text-primary">
              Volver
            </Link>
          </div>
        </form>
      </Card>
    </main>
  )
}

export default ConsumidorFinalScreen
