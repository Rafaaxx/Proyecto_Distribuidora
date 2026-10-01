import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useRef } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import {
  aCuerpoDeUbicacion,
  esquemaUbicacion,
  etiquetaDeTipoDeUbicacion,
  TIPOS_DE_UBICACION,
  type DatosUbicacion,
} from '../../../domain/stock/ubicacionSchema'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import type { Ubicacion } from '../../../features/stock/api'
import { ErrorDeStock } from '../../../features/stock/errores'
import { esErrorDeRed, useCrearUbicacion, useModificarUbicacion, useUbicaciones } from '../../../features/stock/hooks'
import { generarOperationId } from '../../../lib/api/operationId'

const SIN_PERMISO = 'No tenés permiso para administrar ubicaciones.'
const NO_EXISTE = 'La ubicación pedida no existe.'
const AVISO_SIN_CONEXION = 'Se necesita conexión para completar esta operación. Probá de nuevo cuando tengas conexión.'
const AVISO_REQUIERE_CONEXION =
  'Este dato requiere conexión con el servidor y no se guarda para enviar después: si se corta la conexión, volvé a intentarlo.'
const MENSAJE_GENERICO = 'No se pudo completar la operación.'
const VOLVER = '/admin/stock'

function mensajeDeError(error: unknown): string {
  if (esErrorDeRed(error)) return AVISO_SIN_CONEXION
  return error instanceof ErrorDeStock ? error.message : MENSAJE_GENERICO
}

function SinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Ubicación" />
      <p className="text-sm text-primary/70">{SIN_PERMISO}</p>
    </main>
  )
}

/**
 * Alta y edición de una ubicación (change 09, tarea 8.2; `design.md` D2, D7, D8;
 * spec `ubicaciones`). Rutas `/admin/stock/ubicaciones/nueva` y
 * `/admin/stock/ubicaciones/:ubicacionId`. El permiso es `ADMIN_CONFIGURACION`
 * (D2), de `['yo']` vía `<SiTienePermiso>`: sin él, el formulario no se monta.
 *
 * Un vehículo siempre requiere toma (STK-02): el formulario lo marca y no deja
 * quitarlo; el servidor y la base lo repiten. Los rechazos del servidor
 * (`NOMBRE_DUPLICADO`, `UBICACION_CON_STOCK`, ...) se muestran con su mensaje.
 */
export function UbicacionFormScreen() {
  const { ubicacionId } = useParams<{ ubicacionId?: string }>()
  return (
    <SiTienePermiso permiso="ADMIN_CONFIGURACION" fallback={<SinPermiso />}>
      {ubicacionId ? <EdicionDeUbicacion ubicacionId={ubicacionId} /> : <FormularioDeUbicacion />}
    </SiTienePermiso>
  )
}

/** No hay una ruta de lectura por id: la ubicación se busca en el listado, que
 * sigue trayendo páginas hasta encontrarla o agotarse. */
function EdicionDeUbicacion({ ubicacionId }: { ubicacionId: string }) {
  const ubicaciones = useUbicaciones()
  const encontrada = ubicaciones.data?.pages.flatMap((p) => p.items).find((u) => u.id === ubicacionId)
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = ubicaciones

  useEffect(() => {
    if (!encontrada && hasNextPage && !isFetchingNextPage) void fetchNextPage()
  }, [encontrada, hasNextPage, isFetchingNextPage, fetchNextPage])

  if (ubicaciones.isError) {
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo="Ubicación" />
        <Alert>{mensajeDeError(ubicaciones.error)}</Alert>
      </main>
    )
  }
  if (encontrada) return <FormularioDeUbicacion ubicacion={encontrada} />
  if (ubicaciones.isPending || hasNextPage) return <p>Cargando…</p>
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Ubicación" />
      <p className="text-sm text-primary/70">{NO_EXISTE}</p>
    </main>
  )
}

interface EnvioPendiente {
  firma: string
  operationId: string
}

function FormularioDeUbicacion({ ubicacion }: { ubicacion?: Ubicacion }) {
  const navigate = useNavigate()
  const crear = useCrearUbicacion()
  const modificar = useModificarUbicacion()
  // Envío cortado por la red antes de recibir respuesta: su `operation_id` se
  // conserva para reenviarlo si el usuario reintenta lo mismo (INV-06, TR-07).
  const pendienteRef = useRef<EnvioPendiente | null>(null)

  const {
    register,
    handleSubmit,
    setError,
    setValue,
    control,
    formState: { errors, isSubmitting },
  } = useForm<DatosUbicacion>({
    resolver: zodResolver(esquemaUbicacion),
    defaultValues: {
      nombre: ubicacion?.nombre ?? '',
      tipo: (ubicacion?.tipo as DatosUbicacion['tipo'] | undefined) ?? 'DEPOSITO',
      requiere_toma: ubicacion?.requiere_toma ?? false,
      activo: ubicacion?.activo ?? true,
    },
  })
  const tipo = useWatch({ control, name: 'tipo' })
  const esVehiculo = tipo === 'VEHICULO'

  async function enviar(datos: DatosUbicacion) {
    const cuerpo = aCuerpoDeUbicacion(datos)
    const firma = JSON.stringify(cuerpo)
    const operationId =
      pendienteRef.current?.firma === firma ? pendienteRef.current.operationId : generarOperationId()
    try {
      if (ubicacion) {
        await modificar.mutateAsync({ ...cuerpo, ubicacionId: ubicacion.id, operationId })
      } else {
        await crear.mutateAsync({
          nombre: cuerpo.nombre,
          tipo: cuerpo.tipo,
          requiere_toma: cuerpo.requiere_toma,
          operationId,
        })
      }
      pendienteRef.current = null
      navigate(VOLVER)
    } catch (error) {
      // Corte de red: puede que el servidor sí lo haya procesado, así que se
      // reenvía con el mismo `operation_id`. Un rechazo con respuesta HTTP ya
      // está resuelto: reenviar es una operación nueva.
      pendienteRef.current = esErrorDeRed(error) ? { firma, operationId } : null
      setError('root', { message: mensajeDeError(error) })
    }
  }

  const tipoRegistrado = register('tipo', {
    onChange: (evento: { target: { value: string } }) => {
      if (evento.target.value === 'VEHICULO') setValue('requiere_toma', true)
    },
  })

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={ubicacion ? 'Editar ubicación' : 'Nueva ubicación'} />
      <Card>
        <form onSubmit={(evento) => void handleSubmit(enviar)(evento)} noValidate className="flex flex-col gap-4">
          <p className="text-sm text-primary/70">{AVISO_REQUIERE_CONEXION}</p>

          <Campo id="nombre" etiqueta="Nombre" error={errors.nombre?.message}>
            <input id="nombre" autoComplete="off" className="rounded-md border border-border px-2 py-1 text-sm" {...register('nombre')} />
          </Campo>

          <Campo id="tipo" etiqueta="Tipo" error={errors.tipo?.message}>
            <select id="tipo" className="rounded-md border border-border px-2 py-1 text-sm" {...tipoRegistrado}>
              {TIPOS_DE_UBICACION.map((valor) => (
                <option key={valor} value={valor}>
                  {etiquetaDeTipoDeUbicacion(valor)}
                </option>
              ))}
            </select>
          </Campo>

          <div className="flex flex-col gap-1">
            <label className="flex items-center gap-2 text-sm text-primary">
              {/* `aria-disabled` y no `disabled`: un campo deshabilitado no entra en los
                  valores del formulario y el esquema lo vería como faltante. */}
              <input
                type="checkbox"
                aria-disabled={esVehiculo}
                onClick={(evento) => {
                  if (esVehiculo) evento.preventDefault()
                }}
                {...register('requiere_toma')}
              />
              Requiere toma
            </label>
            {esVehiculo && <p className="text-xs text-primary/70">Un vehículo siempre requiere toma.</p>}
            {errors.requiere_toma?.message && (
              <p role="alert" className="text-sm text-danger">
                {errors.requiere_toma.message}
              </p>
            )}
          </div>

          {ubicacion && (
            <label className="flex items-center gap-2 text-sm text-primary">
              <input type="checkbox" {...register('activo')} />
              Activa
            </label>
          )}

          {errors.root?.message && <Alert>{errors.root.message}</Alert>}

          <div className="flex items-center gap-3">
            <Boton type="submit" disabled={isSubmitting}>
              Guardar
            </Boton>
            <Link to={VOLVER} className="text-sm text-primary/70 hover:text-primary">
              Cancelar
            </Link>
          </div>
        </form>
      </Card>
    </main>
  )
}

export default UbicacionFormScreen
