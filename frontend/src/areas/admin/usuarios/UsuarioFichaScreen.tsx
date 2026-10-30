import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { useDatosParaAvisosDeBaja } from '../../../features/identidad/useAvisosDeBaja'
import { usePermisos } from '../../../features/identidad/usePermisos'
import { useRolesConPermisos } from '../../../features/identidad/useRoles'
import { useDesbloquearUsuario, useUsuario } from '../../../features/identidad/useUsuariosAdmin'
import { ErrorDeApiUsuarios, type UsuarioDetalle } from '../../../features/identidad/usuariosApi'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { FichaContrasena } from './FichaContrasena'
import { FichaDatos } from './FichaDatos'
import { FichaEstado } from './FichaEstado'
import { FichaRol } from './FichaRol'
import { FichaTope } from './FichaTope'
import { describirErrorDeUsuarios, estaSinConexion, AVISO_SIN_CONEXION } from './errores'

/**
 * Ficha de un usuario (change 20b, tarea 10.1; D16): datos, rol, tope propio, contraseña,
 * desbloqueo, PIN, clientes asignados y baja o reactivación. Cada sección es un comando
 * auditado con su confirmación; el servidor valida igual (SEG-06). Un usuario de otra
 * organización o inexistente responde 404 y se informa sin datos (INV-21).
 */
export function UsuarioFichaScreen() {
  const { usuarioId } = useParams()
  const usuario = useUsuario(usuarioId)
  const roles = useRolesConPermisos()
  const { yo } = usePermisos()

  if (usuario.isPending) return <p>Cargando…</p>
  if (usuario.isError) {
    const noEncontrado = usuario.error instanceof ErrorDeApiUsuarios && usuario.error.estado === 404
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo="Usuario" />
        <Alert>{noEncontrado ? 'No se encontró ese usuario.' : 'No se pudo obtener el usuario.'}</Alert>
        <Link to="/admin/usuarios" className="text-sm text-primary/70 hover:text-primary hover:underline">
          Volver al listado
        </Link>
      </main>
    )
  }

  const datos = usuario.data
  const rolDelUsuario = roles.data?.find((rol) => rol.id === datos.rol_id)
  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo={datos.nombre}
        acciones={
          <Link to="/admin/usuarios" className="text-sm text-primary/70 hover:text-primary hover:underline">
            Volver al listado
          </Link>
        }
      />
      <FichaDatos key={`${datos.id}:${datos.nombre}:${datos.email ?? ''}`} usuario={datos} />
      <FichaRol
        key={`${datos.id}:${datos.rol_id}`}
        usuario={datos}
        roles={roles.data ?? []}
        esMiUsuario={yo?.usuario.id === datos.id}
      />
      <FichaTope key={`${datos.id}:${datos.tope_descuento_override ?? ''}`} usuario={datos} rol={rolDelUsuario} />
      <FichaContrasena usuarioId={datos.id} />
      <FichaAcceso usuario={datos} />
      <SiTienePermiso permiso="GESTIONAR_CLIENTES">
        <FichaClientesAsignados usuarioId={datos.id} />
      </SiTienePermiso>
      <FichaEstado usuario={datos} />
    </main>
  )
}

/** Desbloqueo del inicio de sesión (ADR-057) y enlace al PIN de autorización (ADR-011, 18b). */
function FichaAcceso({ usuario }: { usuario: UsuarioDetalle }) {
  const desbloquear = useDesbloquearUsuario()
  const operationId = useOperationIdDeEnvio({ usuarioId: usuario.id, accion: 'desbloquear' })
  const [mensaje, setMensaje] = useState<{ tipo: 'ok' | 'error'; texto: string } | null>(null)

  const alDesbloquear = async () => {
    setMensaje(null)
    if (estaSinConexion()) {
      setMensaje({ tipo: 'error', texto: AVISO_SIN_CONEXION })
      return
    }
    try {
      await desbloquear.mutateAsync({ usuarioId: usuario.id, operationId: operationId.obtener() })
      operationId.completar()
      setMensaje({ tipo: 'ok', texto: 'Listo: el inicio de sesión quedó desbloqueado.' })
    } catch (falla) {
      setMensaje({ tipo: 'error', texto: describirErrorDeUsuarios(falla) })
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <h2 className="text-base font-semibold text-primary">Acceso</h2>
      <div className="flex flex-wrap items-center gap-3">
        <Boton variante="secundario" disabled={desbloquear.isPending} onClick={() => void alDesbloquear()}>
          Desbloquear inicio de sesión
        </Boton>
        <Link to="/admin/roles/pin" className="text-sm text-primary/70 hover:text-primary hover:underline">
          PIN de autorización
        </Link>
      </div>
      {mensaje?.tipo === 'error' && <Alert>{mensaje.texto}</Alert>}
      {mensaje?.tipo === 'ok' && (
        <p role="status" className="text-sm text-primary">
          {mensaje.texto}
        </p>
      )}
    </Card>
  )
}

/** "Clientes asignados" con enlace al listado filtrado por el vendedor (D15, D6). */
function FichaClientesAsignados({ usuarioId }: { usuarioId: string }) {
  const datos = useDatosParaAvisosDeBaja(usuarioId)
  const cantidad = datos.clientesAsignados
  const texto =
    cantidad === 0
      ? 'No tiene clientes asignados: al vender y cobrar ve todos los clientes.'
      : datos.masDeLosContados
        ? `Más de ${cantidad} clientes asignados`
        : `${cantidad} ${cantidad === 1 ? 'cliente asignado' : 'clientes asignados'}`
  return (
    <Card className="flex flex-col gap-2">
      <h2 className="text-base font-semibold text-primary">Clientes asignados</h2>
      {!datos.cargando && <p className="text-sm text-primary">{texto}</p>}
      {cantidad > 0 && (
        <Link
          to={`/admin/clientes?vendedor_id=${usuarioId}`}
          className="text-sm text-primary/70 hover:text-primary hover:underline"
        >
          Ver clientes asignados
        </Link>
      )}
    </Card>
  )
}

export default UsuarioFichaScreen
