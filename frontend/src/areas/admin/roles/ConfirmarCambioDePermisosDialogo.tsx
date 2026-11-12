import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import { diferenciaDePermisos, mensajeDeErrorDeRol, perdeLaAutorizacion } from '../../../domain/identidad/roles'
import { ErrorDeApiRoles, type PermisoDeCatalogo, type RolConPermisos } from '../../../features/identidad/rolesApi'
import { useCambiarPermisosDeRol } from '../../../features/identidad/useRoles'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { esErrorDeRed } from '../../../lib/api/reintentoDeRed'
import { AVISO_SIN_CONEXION, estaSinConexion } from '../precios/errores'

const MENSAJE_GENERICO = 'No se pudo completar la operación.'

interface ConfirmarCambioDePermisosDialogoProps {
  rol: RolConPermisos
  catalogo: PermisoDeCatalogo[]
  /** El conjunto completo de permisos que quedaría. */
  nuevos: string[]
  esMiRol: boolean
  onCerrar: () => void
}

function describirError(error: unknown): string {
  if (esErrorDeRed(error)) return AVISO_SIN_CONEXION
  if (error instanceof ErrorDeApiRoles) return mensajeDeErrorDeRol(error.codigo, error.message)
  return MENSAJE_GENERICO
}

function nombres(codigos: string[], catalogo: PermisoDeCatalogo[]): string {
  return codigos.map((codigo) => catalogo.find((p) => p.codigo === codigo)?.descripcion ?? codigo).join(', ')
}

/**
 * Confirmación del cambio de permisos de un rol (change 17b, tarea 9.1; D9; ADR-011, ADR-053).
 * Muestra "Agrega: … / Quita: …" y los avisos: se borra el PIN de los usuarios si el rol se queda
 * sin permisos de autorización, y se está cambiando el propio rol. Nada se envía antes de
 * confirmar; el reintento del mismo cambio reenvía el mismo `Operation-Id` (INV-06).
 */
export function ConfirmarCambioDePermisosDialogo({
  rol,
  catalogo,
  nuevos,
  esMiRol,
  onCerrar,
}: ConfirmarCambioDePermisosDialogoProps) {
  const cambiar = useCambiarPermisosDeRol()
  const [error, setError] = useState<string | null>(null)
  const { agrega, quita } = diferenciaDePermisos(rol.permisos, nuevos, catalogo)
  const operationId = useOperationIdDeEnvio({ rolId: rol.id, permisos: [...nuevos].sort() })

  const confirmar = async () => {
    if (estaSinConexion()) {
      setError(AVISO_SIN_CONEXION)
      return
    }
    try {
      await cambiar.mutateAsync({ rolId: rol.id, permisos: [...nuevos].sort(), operationId: operationId.obtener() })
      operationId.completar()
      onCerrar()
    } catch (falla) {
      setError(describirError(falla))
    }
  }

  return (
    <Dialogo abierto titulo={`Confirmar cambios en ${rol.nombre}`} onCerrar={onCerrar}>
      <div className="flex flex-col gap-3 text-sm text-primary">
        {agrega.length > 0 && <p>Agrega: {nombres(agrega, catalogo)}</p>}
        {quita.length > 0 && <p>Quita: {nombres(quita, catalogo)}</p>}
        {perdeLaAutorizacion(rol.permisos, nuevos) && (
          <Alert>
            Se va a borrar el PIN de autorización de los usuarios del rol ({rol.usuarios_activos} activos). Si después les devolvés
            algún permiso de autorización, cada uno tendrá que crear un PIN nuevo.
          </Alert>
        )}
        {esMiRol && <Alert>Estás cambiando tu propio rol: lo que cambie vale también para vos desde tu próxima acción.</Alert>}
        {error && <Alert>{error}</Alert>}
        <div className="flex gap-2">
          <Boton disabled={cambiar.isPending} onClick={() => void confirmar()}>
            Confirmar cambios
          </Boton>
          <Boton variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
        </div>
      </div>
    </Dialogo>
  )
}
