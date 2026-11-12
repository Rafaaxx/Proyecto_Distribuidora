import { zodResolver } from '@hookform/resolvers/zod'
import { useForm, useWatch } from 'react-hook-form'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { describirTope, topeEscritoDesdeFraccion } from '../../../domain/identidad/topes'
import { esquemaTopePropio, topePropioSinEfecto } from '../../../domain/identidad/usuarios'
import type { RolConPermisos } from '../../../features/identidad/rolesApi'
import { useDefinirTopeDeUsuario } from '../../../features/identidad/useUsuariosAdmin'
import type { UsuarioDetalle } from '../../../features/identidad/usuariosApi'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { describirErrorDeUsuarios, estaSinConexion, AVISO_SIN_CONEXION } from './errores'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

interface FormularioDeTope {
  tope_descuento: string
}

/**
 * Tope de descuento propio (change 20b, D12; DSC-06, INV-03): se escribe como porcentaje y viaja
 * como fracción string; vacío vuelve al tope del rol. Avisa que no tiene efecto si el rol no
 * tiene descuento manual.
 */
export function FichaTope({ usuario, rol }: { usuario: UsuarioDetalle; rol: RolConPermisos | undefined }) {
  const definir = useDefinirTopeDeUsuario()
  const {
    register,
    handleSubmit,
    setError,
    control,
    formState: { errors, isSubmitSuccessful },
  } = useForm<FormularioDeTope, unknown, { tope_descuento: string | null }>({
    resolver: zodResolver(esquemaTopePropio),
    defaultValues: {
      tope_descuento: usuario.tope_descuento_override === null ? '' : topeEscritoDesdeFraccion(usuario.tope_descuento_override),
    },
  })
  const escrito = useWatch({ control, name: 'tope_descuento' })
  const operationId = useOperationIdDeEnvio({ usuarioId: usuario.id, tope: escrito.trim().replace(',', '.') })
  const propioEscrito = esquemaTopePropio.safeParse({ tope_descuento: escrito })
  const sinEfecto =
    rol !== undefined && propioEscrito.success && topePropioSinEfecto(rol.permisos, propioEscrito.data.tope_descuento)

  const alEnviar = handleSubmit(async (datos) => {
    if (estaSinConexion()) {
      setError('root', { message: AVISO_SIN_CONEXION })
      return
    }
    try {
      await definir.mutateAsync({ usuarioId: usuario.id, topeDescuento: datos.tope_descuento, operationId: operationId.obtener() })
      operationId.completar()
    } catch (falla) {
      setError('root', { message: describirErrorDeUsuarios(falla) })
    }
  })

  return (
    <Card>
      <form onSubmit={alEnviar} noValidate className="flex flex-col gap-3" aria-label="Tope de descuento propio">
        <h2 className="flex items-center gap-2 text-base font-semibold text-primary">
          Tope de descuento propio <Ayuda clave="usuarios.topePropio" />
        </h2>
        <p className="text-sm text-primary/70">
          Tope del rol: {rol ? describirTope(rol.tope_descuento) : '—'}. Dejalo vacío para que rija el del rol; 100 % es "Sin tope".
        </p>
        <Campo id="ficha-tope" etiqueta="Tope propio (%)" error={errors.tope_descuento?.message}>
          <input id="ficha-tope" inputMode="decimal" className={CLASE_CONTROL} {...register('tope_descuento')} />
        </Campo>
        {sinEfecto && <Alert>No tiene efecto mientras su rol no tenga el permiso de descuento manual.</Alert>}
        {errors.root?.message && <Alert>{errors.root.message}</Alert>}
        {isSubmitSuccessful && !errors.root && (
          <p role="status" className="text-sm text-primary">
            Listo: el tope quedó guardado. Rige desde la próxima venta con conexión.
          </p>
        )}
        <div>
          <Boton type="submit" disabled={definir.isPending}>
            Guardar tope
          </Boton>
        </div>
      </form>
    </Card>
  )
}
