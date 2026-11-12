import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import { Campo } from '../../../components/ui/Field'
import { esquemaNombreDeRol, esquemaNuevoRol, rolesAsignables } from '../../../domain/identidad/usuarios'
import type { RolConPermisos } from '../../../features/identidad/rolesApi'
import { useCrearRol, useDarDeBajaRol, useRenombrarRol } from '../../../features/identidad/useRoles'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { describirErrorDeUsuarios, estaSinConexion, AVISO_SIN_CONEXION } from '../usuarios/errores'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

interface FormularioDeNombre {
  nombre: string
  copiarDe: string
}

/**
 * "Nuevo rol" (change 20b, D10): nombre y, si se quiere, "copiar permisos de" otro rol activo. La
 * copia es solo de interfaz: el comando recibe la lista de permisos. El tope de descuento nace en
 * 0 % y se cambia desde "Topes por rol". El reintento reenvía el mismo `Operation-Id` mientras no
 * cambie lo escrito (INV-06).
 */
export function NuevoRolDialogo({ roles, onCerrar }: { roles: readonly RolConPermisos[]; onCerrar: () => void }) {
  const crear = useCrearRol()
  const {
    register,
    handleSubmit,
    setError,
    control,
    formState: { errors },
  } = useForm<FormularioDeNombre, unknown, FormularioDeNombre>({
    resolver: zodResolver(esquemaNuevoRol),
    defaultValues: { nombre: '', copiarDe: '' },
  })
  const escrito = useWatch({ control })
  const operationId = useOperationIdDeEnvio({ nombre: escrito.nombre?.trim(), copiarDe: escrito.copiarDe })

  const alEnviar = handleSubmit(async (datos) => {
    if (estaSinConexion()) {
      setError('root', { message: AVISO_SIN_CONEXION })
      return
    }
    const origen = roles.find((rol) => rol.id === escrito.copiarDe)
    try {
      await crear.mutateAsync({
        nombre: datos.nombre,
        permisos: [...(origen?.permisos ?? [])].sort(),
        operationId: operationId.obtener(),
      })
      operationId.completar()
      onCerrar()
    } catch (falla) {
      setError('root', { message: describirErrorDeUsuarios(falla) })
    }
  })

  return (
    <Dialogo abierto titulo="Nuevo rol" onCerrar={onCerrar}>
      <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
        <Campo id="nuevo-rol-nombre" etiqueta="Nombre del rol" error={errors.nombre?.message}>
          <input id="nuevo-rol-nombre" className={CLASE_CONTROL} {...register('nombre')} />
        </Campo>
        <Campo id="nuevo-rol-copiar" etiqueta="Copiar permisos de">
          <select id="nuevo-rol-copiar" className={CLASE_CONTROL} {...register('copiarDe')}>
            <option value="">No copiar: arranca sin permisos</option>
            {rolesAsignables(roles).map((rol) => (
              <option key={rol.id} value={rol.id}>
                {rol.nombre}
              </option>
            ))}
          </select>
        </Campo>
        <p className="text-sm text-primary/70">
          El tope de descuento arranca en 0 %: se cambia en «Topes por rol». Los permisos se pueden ajustar después.
        </p>
        {errors.root?.message && <Alert>{errors.root.message}</Alert>}
        <div className="flex gap-2">
          <Boton type="submit" disabled={crear.isPending}>
            Crear rol
          </Boton>
          <Boton variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
        </div>
      </form>
    </Dialogo>
  )
}

/** "Renombrar" (change 20b, D10): el nombre es único por organización, aunque el otro rol esté de baja. */
export function RenombrarRolDialogo({ rol, onCerrar }: { rol: RolConPermisos; onCerrar: () => void }) {
  const renombrar = useRenombrarRol()
  const {
    register,
    handleSubmit,
    setError,
    control,
    formState: { errors },
  } = useForm<{ nombre: string }, unknown, { nombre: string }>({
    resolver: zodResolver(esquemaNombreDeRol),
    defaultValues: { nombre: rol.nombre },
  })
  const escrito = useWatch({ control, name: 'nombre' })
  const operationId = useOperationIdDeEnvio({ rolId: rol.id, nombre: escrito.trim() })

  const alEnviar = handleSubmit(async (datos) => {
    if (estaSinConexion()) {
      setError('root', { message: AVISO_SIN_CONEXION })
      return
    }
    try {
      await renombrar.mutateAsync({ rolId: rol.id, nombre: datos.nombre, operationId: operationId.obtener() })
      operationId.completar()
      onCerrar()
    } catch (falla) {
      setError('root', { message: describirErrorDeUsuarios(falla) })
    }
  })

  return (
    <Dialogo abierto titulo={`Renombrar ${rol.nombre}`} onCerrar={onCerrar}>
      <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
        <Campo id="renombrar-rol-nombre" etiqueta="Nombre del rol" error={errors.nombre?.message}>
          <input id="renombrar-rol-nombre" className={CLASE_CONTROL} {...register('nombre')} />
        </Campo>
        {errors.root?.message && <Alert>{errors.root.message}</Alert>}
        <div className="flex gap-2">
          <Boton type="submit" disabled={renombrar.isPending}>
            Guardar nombre
          </Boton>
          <Boton variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
        </div>
      </form>
    </Dialogo>
  )
}

/**
 * "Dar de baja" un rol con confirmación (change 20b, D11; ADR-028, ADR-053): se rechaza si tiene
 * usuarios activos (el mensaje dice cuántos) o si dejaría la organización sin administrador. Un
 * rol de baja no se asigna ni aparece en los selectores.
 */
export function BajaDeRolDialogo({ rol, onCerrar }: { rol: RolConPermisos; onCerrar: () => void }) {
  const baja = useDarDeBajaRol()
  const [error, setError] = useState<string | null>(null)
  const operationId = useOperationIdDeEnvio({ rolId: rol.id, accion: 'baja' })

  const confirmar = async () => {
    if (estaSinConexion()) {
      setError(AVISO_SIN_CONEXION)
      return
    }
    try {
      await baja.mutateAsync({ rolId: rol.id, operationId: operationId.obtener() })
      operationId.completar()
      onCerrar()
    } catch (falla) {
      setError(describirErrorDeUsuarios(falla, { usuariosActivos: rol.usuarios_activos }))
    }
  }

  return (
    <Dialogo abierto titulo={`Confirmar baja del rol ${rol.nombre}`} onCerrar={onCerrar}>
      <div className="flex flex-col gap-3 text-sm text-primary">
        <p className="flex items-center gap-1">
          El rol deja de ofrecerse al asignar roles. Sus permisos se conservan y lo podés reactivar cuando quieras.
          <Ayuda clave="roles.baja" />
        </p>
        {error && <Alert>{error}</Alert>}
        <div className="flex gap-2">
          <Boton variante="peligro" disabled={baja.isPending} onClick={() => void confirmar()}>
            Confirmar baja del rol
          </Boton>
          <Boton variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
        </div>
      </div>
    </Dialogo>
  )
}
