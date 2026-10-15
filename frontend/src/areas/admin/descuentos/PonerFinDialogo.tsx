import { zodResolver } from '@hookform/resolvers/zod'
import { useMemo } from 'react'
import { useForm, useWatch } from 'react-hook-form'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import { Campo } from '../../../components/ui/Field'
import { crearEsquemaFinDeVigencia } from '../../../domain/descuentos/formulario'
import { useModificarReglaDescuento } from '../../../features/descuentos/hooks'
import { campoDeReglaDeDescuentoParaCodigo, mensajeDeErrorDeDescuentos } from '../../../features/descuentos/mapaErrorACampo'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { AVISO_SIN_CONEXION, describirError, estaSinConexion } from './errores'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

interface PonerFinDialogoProps {
  reglaId: string
  vigenciaDesde: string | null
  onCerrar: () => void
  onEstadoInvalido: (mensaje: string) => void
  onHecho: () => void
}

interface FormularioDeFin {
  vigencia_hasta: string
}

/**
 * "Poner fin" a una regla activada o pausada: fija su vigencia hasta (change 16, tarea 15.3; D15,
 * D16). Es lo único que cambia de una regla activada: el `PUT` lleva solo ese campo.
 * `VIGENCIA_INVALIDA` del servidor se muestra junto a la fecha.
 */
export function PonerFinDialogo({ reglaId, vigenciaDesde, onCerrar, onEstadoInvalido, onHecho }: PonerFinDialogoProps) {
  const modificar = useModificarReglaDescuento()
  const esquema = useMemo(() => crearEsquemaFinDeVigencia(vigenciaDesde), [vigenciaDesde])
  const {
    register,
    handleSubmit,
    setError,
    control,
    formState: { errors },
  } = useForm<FormularioDeFin, unknown, { vigencia_hasta: string | null }>({
    resolver: zodResolver(esquema),
    defaultValues: { vigencia_hasta: '' },
  })
  const escrito = useWatch({ control, name: 'vigencia_hasta' })
  const operationId = useOperationIdDeEnvio({ reglaId, fin: escrito })

  const alEnviar = handleSubmit(async (datos) => {
    if (estaSinConexion()) {
      setError('root', { message: AVISO_SIN_CONEXION })
      return
    }
    try {
      await modificar.mutateAsync({ reglaId, vigencia_hasta: datos.vigencia_hasta, operationId: operationId.obtener() })
      operationId.completar()
      onHecho()
    } catch (falla) {
      const { codigo, mensaje } = describirError(falla)
      if (codigo === 'REGLA_ESTADO_INVALIDO' || codigo === 'REGLA_NO_ES_BORRADOR') {
        onEstadoInvalido(mensajeDeErrorDeDescuentos('REGLA_ESTADO_INVALIDO', mensaje))
        return
      }
      const campo = codigo === null ? null : campoDeReglaDeDescuentoParaCodigo(codigo)
      setError(campo === 'vigencia_hasta' ? 'vigencia_hasta' : 'root', { message: mensajeDeErrorDeDescuentos(codigo, mensaje) })
    }
  })

  return (
    <Dialogo abierto titulo="Poner fin a la regla" onCerrar={onCerrar}>
      <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
        <p className="text-sm text-primary/80">
          Fijá hasta cuándo rige la regla. Después de esa fecha deja de aplicarse y se ve como vencida.
        </p>
        <Campo id="fin-vigencia-hasta" etiqueta="Vigencia hasta" error={errors.vigencia_hasta?.message}>
          <input id="fin-vigencia-hasta" type="datetime-local" className={CLASE_CONTROL} {...register('vigencia_hasta')} />
        </Campo>
        {errors.root?.message && <Alert>{errors.root.message}</Alert>}
        <div className="flex gap-2">
          <Boton type="submit" disabled={modificar.isPending}>
            Confirmar fin
          </Boton>
          <Boton variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
        </div>
      </form>
    </Dialogo>
  )
}
