import { zodResolver } from '@hookform/resolvers/zod'
import { useForm, useWatch } from 'react-hook-form'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import { Campo } from '../../../components/ui/Field'
import { describirTope, esquemaTope, topeEscritoDesdeFraccion } from '../../../domain/identidad/topes'
import type { RolConTope } from '../../../features/descuentos/api'
import { useDefinirTopeDeRol } from '../../../features/descuentos/hooks'
import { campoDeTopeParaCodigo } from '../../../features/descuentos/mapaErrorACampo'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { AVISO_SIN_CONEXION, describirError, estaSinConexion } from './errores'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

interface TopeDialogoProps {
  rol: RolConTope
  onCerrar: () => void
}

interface FormularioDeTope {
  tope_descuento: string
}

/** Resumen del cambio mientras se escribe: "de 0 % a 5 %" (vacío si lo escrito no es un tope válido). */
function resumenDelCambio(actual: string, escrito: string): string | null {
  const resultado = esquemaTope.safeParse({ tope_descuento: escrito })
  return resultado.success ? `de ${describirTope(actual)} a ${describirTope(resultado.data.tope_descuento)}` : null
}

/**
 * Definir el tope de descuento manual de un rol, con confirmación (change 16, tarea 15.4, D13).
 * La persona escribe un porcentaje; el comando lleva la fracción de seis decimales como cadena
 * (`"0.050000"`). El resumen "de X a Y" se ve antes de confirmar. Sin conexión no se envía; el
 * reintento del mismo tope reenvía el mismo `Operation-Id` (INV-06). El servidor valida igual
 * (`IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO`).
 */
export function TopeDialogo({ rol, onCerrar }: TopeDialogoProps) {
  const definir = useDefinirTopeDeRol()
  const {
    register,
    handleSubmit,
    setError,
    control,
    formState: { errors },
  } = useForm<FormularioDeTope, unknown, { tope_descuento: string }>({
    resolver: zodResolver(esquemaTope),
    defaultValues: { tope_descuento: topeEscritoDesdeFraccion(rol.tope_descuento) },
  })
  const escrito = useWatch({ control, name: 'tope_descuento' })
  const operationId = useOperationIdDeEnvio({ rolId: rol.id, tope: escrito.trim().replace(',', '.') })
  const resumen = resumenDelCambio(rol.tope_descuento, escrito)

  const alEnviar = handleSubmit(async (datos) => {
    if (estaSinConexion()) {
      setError('root', { message: AVISO_SIN_CONEXION })
      return
    }
    try {
      await definir.mutateAsync({ rolId: rol.id, tope_descuento: datos.tope_descuento, operationId: operationId.obtener() })
      operationId.completar()
      onCerrar()
    } catch (falla) {
      const { codigo, mensaje } = describirError(falla)
      const campo = codigo === null ? null : campoDeTopeParaCodigo(codigo)
      setError(campo ?? 'root', { message: mensaje })
    }
  })

  return (
    <Dialogo abierto titulo={`Tope de descuento de ${rol.nombre}`} onCerrar={onCerrar}>
      <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
        <Campo id="tope-descuento" etiqueta="Tope de descuento (%)" error={errors.tope_descuento?.message}>
          <input id="tope-descuento" inputMode="decimal" className={CLASE_CONTROL} {...register('tope_descuento')} />
        </Campo>
        {resumen && (
          <p className="text-sm text-primary">
            Se va a cambiar el tope de «{rol.nombre}» {resumen}.
          </p>
        )}
        <p className="text-sm text-primary/70">100 % es "Sin tope". Con 0 %, todo descuento manual necesita autorización.</p>
        {errors.root?.message && <Alert>{errors.root.message}</Alert>}
        <div className="flex gap-2">
          <Boton type="submit" disabled={definir.isPending}>
            Confirmar tope
          </Boton>
          <Boton variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
        </div>
      </form>
    </Dialogo>
  )
}
