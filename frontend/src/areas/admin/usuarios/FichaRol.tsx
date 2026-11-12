import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Dialogo } from '../../../components/ui/Dialog'
import { Campo } from '../../../components/ui/Field'
import { rolesAsignables } from '../../../domain/identidad/usuarios'
import type { RolConPermisos } from '../../../features/identidad/rolesApi'
import { useCambiarRolDeUsuario } from '../../../features/identidad/useUsuariosAdmin'
import type { UsuarioDetalle } from '../../../features/identidad/usuariosApi'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { describirErrorDeUsuarios, estaSinConexion, AVISO_SIN_CONEXION } from './errores'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

interface FichaRolProps {
  usuario: UsuarioDetalle
  roles: readonly RolConPermisos[]
  esMiUsuario: boolean
}

/**
 * Cambio de rol de un usuario con confirmación (change 20b, D7, D5; ADR-017, ADR-011, ADR-053).
 * El selector ofrece solo roles activos; cambiar el propio rol lo avisa. Tras guardar se vuelve a
 * pedir la sesión propia (`['yo']`, ADR-027).
 */
export function FichaRol({ usuario, roles, esMiUsuario }: FichaRolProps) {
  const [elegido, setElegido] = useState(usuario.rol_id)
  const [confirmando, setConfirmando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const cambiar = useCambiarRolDeUsuario()
  const operationId = useOperationIdDeEnvio({ usuarioId: usuario.id, rolId: elegido })
  const opciones = rolesAsignables(roles, usuario.rol_id)
  const rolNuevo = roles.find((rol) => rol.id === elegido)

  const confirmar = async () => {
    if (estaSinConexion()) {
      setError(AVISO_SIN_CONEXION)
      return
    }
    try {
      await cambiar.mutateAsync({ usuarioId: usuario.id, rolId: elegido, operationId: operationId.obtener() })
      operationId.completar()
      setConfirmando(false)
      setError(null)
    } catch (falla) {
      setError(describirErrorDeUsuarios(falla))
    }
  }

  const cerrar = () => {
    setConfirmando(false)
    setError(null)
  }

  return (
    <Card className="flex flex-col gap-3">
      <h2 className="flex items-center gap-2 text-base font-semibold text-primary">
        Rol <Ayuda clave="usuarios.cambioDeRol" />
      </h2>
      {!usuario.rol_activo && <Alert>El rol actual ({usuario.rol_nombre}) está dado de baja: asignale un rol activo.</Alert>}
      <Campo id="ficha-rol" etiqueta="Rol">
        <select id="ficha-rol" className={CLASE_CONTROL} value={elegido} onChange={(evento) => setElegido(evento.target.value)}>
          {opciones.map((rol) => (
            <option key={rol.id} value={rol.id}>
              {rol.activo ? rol.nombre : `${rol.nombre} (de baja)`}
            </option>
          ))}
        </select>
      </Campo>
      <div>
        <Boton disabled={elegido === usuario.rol_id} onClick={() => setConfirmando(true)}>
          Cambiar rol
        </Boton>
      </div>
      {confirmando && (
        <Dialogo abierto titulo="Confirmar cambio de rol" onCerrar={cerrar}>
          <div className="flex flex-col gap-3 text-sm text-primary">
            <p>
              Vas a cambiar el rol de {usuario.nombre} de «{usuario.rol_nombre}» a «{rolNuevo?.nombre ?? ''}». Rige desde su próxima
              acción.
            </p>
            {esMiUsuario && <Alert>Vas a cambiar tu propio acceso: lo que cambie vale también para vos desde tu próxima acción.</Alert>}
            {error && <Alert>{error}</Alert>}
            <div className="flex gap-2">
              <Boton disabled={cambiar.isPending} onClick={() => void confirmar()}>
                Confirmar cambio de rol
              </Boton>
              <Boton variante="secundario" onClick={cerrar}>
                Cancelar
              </Boton>
            </div>
          </div>
        </Dialogo>
      )}
    </Card>
  )
}
