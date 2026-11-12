import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import type { RolConPermisos } from '../../../features/identidad/rolesApi'
import { useCatalogoDePermisos, useReactivarRol, useRolesConPermisos } from '../../../features/identidad/useRoles'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { describirErrorDeUsuarios } from '../usuarios/errores'
import { BajaDeRolDialogo, NuevoRolDialogo, RenombrarRolDialogo } from './RolDialogos'
import { RolPermisosEditor } from './RolPermisosEditor'

const TITULO = 'Roles y permisos'

function SinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} />
      <p className="text-sm text-primary/70">No tenés permiso para administrar usuarios, roles y permisos.</p>
    </main>
  )
}

/**
 * Roles y permisos (change 17b, tarea 9.1, gobernanza crítica, diseño D9-A; spec
 * `identidad/administracion-de-roles`; `01` §19, ADR-011, ADR-017, ADR-053). Lista los roles con su
 * estado, su cantidad de permisos y de usuarios activos; al elegir uno se editan sus permisos
 * agrupados por módulo. Con `ADMIN_USUARIOS` (ADR-027). Desde el change 20b también crea,
 * renombra, da de baja y reactiva roles (D10, D11); un rol de baja se marca "De baja". El servidor
 * valida igual (SEG-06).
 */
export function RolesScreen() {
  return (
    <SiTienePermiso permiso="ADMIN_USUARIOS" fallback={<SinPermiso />}>
      <RolesListado />
    </SiTienePermiso>
  )
}

function RolesListado() {
  const roles = useRolesConPermisos()
  const catalogo = useCatalogoDePermisos()
  const [elegidoId, setElegidoId] = useState<string | null>(null)
  const [dialogo, setDialogo] = useState<{ tipo: 'nuevo' } | { tipo: 'renombrar' | 'baja'; rolId: string } | null>(null)
  const [errorDeReactivacion, setErrorDeReactivacion] = useState<string | null>(null)
  const elegido = roles.data?.find((r) => r.id === elegidoId)
  const rolDelDialogo =
    dialogo !== null && dialogo.tipo !== 'nuevo' ? roles.data?.find((r) => r.id === dialogo.rolId) : undefined

  const columnas: ColumnaTabla<RolConPermisos>[] = [
    { clave: 'rol', encabezado: 'Rol', render: (r) => <span className="font-medium text-primary">{r.nombre}</span> },
    {
      clave: 'estado',
      encabezado: 'Estado',
      render: (r) => <Badge variante={r.activo ? 'positivo' : 'negativo'}>{r.activo ? 'Activo' : 'De baja'}</Badge>,
    },
    { clave: 'permisos', encabezado: 'Permisos', render: (r) => r.permisos.length },
    { clave: 'usuarios', encabezado: 'Usuarios activos', render: (r) => r.usuarios_activos },
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      render: (r) => (
        <div className="flex flex-wrap gap-2">
          <Boton
            variante="secundario"
            aria-label={`Editar permisos de ${r.nombre}`}
            onClick={() => setElegidoId(r.id)}
          >
            Editar permisos
          </Boton>
          <Boton
            variante="secundario"
            aria-label={`Renombrar ${r.nombre}`}
            onClick={() => setDialogo({ tipo: 'renombrar', rolId: r.id })}
          >
            Renombrar
          </Boton>
          {r.activo ? (
            <Boton
              variante="secundario"
              aria-label={`Dar de baja ${r.nombre}`}
              onClick={() => setDialogo({ tipo: 'baja', rolId: r.id })}
            >
              Dar de baja
            </Boton>
          ) : (
            <BotonReactivar rol={r} onError={setErrorDeReactivacion} />
          )}
        </div>
      ),
    },
  ]

  const hayError = roles.isError || catalogo.isError

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo={TITULO}
        acciones={
          <>
            <Boton onClick={() => setDialogo({ tipo: 'nuevo' })}>Nuevo rol</Boton>
            <SiTienePermiso permiso="GESTIONAR_DESCUENTOS">
              <Link to="/admin/descuentos/topes" className="text-sm text-primary/70 hover:text-primary hover:underline">
                Topes por rol
              </Link>
            </SiTienePermiso>
          </>
        }
      />
      <p className="text-sm text-primary/70">
        Cada rol es una plantilla de permisos. Elegí un rol para ver y cambiar lo que pueden hacer sus usuarios.
      </p>
      {(roles.isPending || catalogo.isPending) && !hayError && <p>Cargando…</p>}
      {hayError && <Alert>No se pudieron obtener los roles y los permisos.</Alert>}
      {errorDeReactivacion && <Alert>{errorDeReactivacion}</Alert>}
      {roles.isSuccess && roles.data.length === 0 && <p className="text-sm text-primary/70">No hay roles.</p>}
      {roles.isSuccess && roles.data.length > 0 && (
        <Card>
          <Tabla filas={roles.data} columnas={columnas} obtenerClave={(r) => r.id} etiqueta={TITULO} />
        </Card>
      )}
      {elegido && catalogo.isSuccess && (
        <RolPermisosEditor
          key={`${elegido.id}:${elegido.permisos.join(',')}`}
          rol={elegido}
          catalogo={catalogo.data}
          onCerrar={() => setElegidoId(null)}
        />
      )}
      {dialogo?.tipo === 'nuevo' && <NuevoRolDialogo roles={roles.data ?? []} onCerrar={() => setDialogo(null)} />}
      {dialogo?.tipo === 'renombrar' && rolDelDialogo && (
        <RenombrarRolDialogo key={rolDelDialogo.id} rol={rolDelDialogo} onCerrar={() => setDialogo(null)} />
      )}
      {dialogo?.tipo === 'baja' && rolDelDialogo && (
        <BajaDeRolDialogo key={rolDelDialogo.id} rol={rolDelDialogo} onCerrar={() => setDialogo(null)} />
      )}
    </main>
  )
}

/** Reactivar un rol de baja: libre, sin confirmación (D11). Un reintento reenvía el mismo `Operation-Id`. */
function BotonReactivar({ rol, onError }: { rol: RolConPermisos; onError: (mensaje: string | null) => void }) {
  const reactivar = useReactivarRol()
  const operationId = useOperationIdDeEnvio({ rolId: rol.id, accion: 'reactivar' })
  const alReactivar = async () => {
    onError(null)
    try {
      await reactivar.mutateAsync({ rolId: rol.id, operationId: operationId.obtener() })
      operationId.completar()
    } catch (falla) {
      onError(describirErrorDeUsuarios(falla))
    }
  }
  return (
    <Boton variante="secundario" aria-label={`Reactivar ${rol.nombre}`} disabled={reactivar.isPending} onClick={() => void alReactivar()}>
      Reactivar
    </Boton>
  )
}

export default RolesScreen
