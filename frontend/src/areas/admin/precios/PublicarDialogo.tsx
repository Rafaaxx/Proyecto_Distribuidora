import { zodResolver } from '@hookform/resolvers/zod'
import { useForm, useWatch, type Resolver } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import { Campo } from '../../../components/ui/Field'
import { resumenDePublicacion } from '../../../domain/precios/presentacion'
import { construirVigencia, crearEsquemaDePublicacion, type VigenciaCargada } from '../../../domain/precios/publicacionSchema'
import { usePublicarVersion } from '../../../features/precios/hooks'
import { campoDePublicacionParaCodigo } from '../../../features/precios/mapaErrorACampo'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { AVISO_SIN_CONEXION, describirError, estaSinConexion } from './errores'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

interface PublicarDialogoProps {
  listaId: string
  versionId: string
  cantidadDePrecios: number
  cantidadSinPrecio: number
  abierto: boolean
  onCerrar: () => void
}

/**
 * Publicación del borrador con confirmación (change 13, tarea 13.3; PRC-02, PRC-06, D6). Informa
 * cuántos precios se publican y cuántos productos quedan sin precio. Las vigencias son opcionales:
 * sin `vigencia_desde` rige desde la publicación. `VIGENCIA_INVALIDA` y `VIGENCIA_DUPLICADA` se
 * muestran junto a la fecha. Solo la ofrece quien tiene `PUBLICAR_LISTAS`.
 */
export function PublicarDialogo(props: PublicarDialogoProps) {
  if (!props.abierto) return null
  return <FormularioDePublicacion {...props} />
}

const resolverDePublicacion: Resolver<VigenciaCargada, unknown, VigenciaCargada> = (valores, contexto, opciones) =>
  zodResolver(crearEsquemaDePublicacion(new Date()))(valores, contexto, opciones)

function FormularioDePublicacion({
  listaId,
  versionId,
  cantidadDePrecios,
  cantidadSinPrecio,
  onCerrar,
}: PublicarDialogoProps) {
  const navigate = useNavigate()
  const publicar = usePublicarVersion()
  const {
    register,
    handleSubmit,
    setError,
    control,
    formState: { errors },
  } = useForm<VigenciaCargada, unknown, VigenciaCargada>({
    resolver: resolverDePublicacion,
    defaultValues: { vigencia_desde: '', vigencia_hasta: '' },
  })
  const [desde, hasta] = useWatch({ control, name: ['vigencia_desde', 'vigencia_hasta'] })
  const operationId = useOperationIdDeEnvio({ listaId, versionId, desde, hasta })

  const alEnviar = handleSubmit(async (datos) => {
    if (estaSinConexion()) {
      setError('root', { message: AVISO_SIN_CONEXION })
      return
    }
    try {
      await publicar.mutateAsync({ listaId, versionId, ...construirVigencia(datos), operationId: operationId.obtener() })
      operationId.completar()
      onCerrar()
      navigate(`/admin/precios/${listaId}`)
    } catch (error) {
      const { codigo, mensaje } = describirError(error)
      const campo = codigo === null ? null : campoDePublicacionParaCodigo(codigo)
      setError(campo ?? 'root', { message: mensaje })
    }
  })

  return (
    <Dialogo abierto titulo="Publicar borrador" onCerrar={onCerrar}>
      <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
        <p className="text-sm text-primary">Se publican {resumenDePublicacion(cantidadDePrecios, cantidadSinPrecio)}.</p>
        <p className="text-sm text-primary/70">
          Una versión publicada no se puede modificar: las correcciones se hacen con una versión nueva. Sin vigencia
          desde, rige desde el momento de la publicación.
        </p>
        <Campo id="vigencia-desde" etiqueta="Vigencia desde (opcional)" error={errors.vigencia_desde?.message}>
          <input id="vigencia-desde" type="datetime-local" className={CLASE_CONTROL} {...register('vigencia_desde')} />
        </Campo>
        <Campo id="vigencia-hasta" etiqueta="Vigencia hasta (opcional)" error={errors.vigencia_hasta?.message}>
          <input id="vigencia-hasta" type="datetime-local" className={CLASE_CONTROL} {...register('vigencia_hasta')} />
        </Campo>
        {errors.root?.message && <Alert>{errors.root.message}</Alert>}
        <div className="flex gap-2">
          <Boton type="submit" disabled={publicar.isPending}>
            Confirmar publicación
          </Boton>
          <Boton type="button" variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
        </div>
      </form>
    </Dialogo>
  )
}
