import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { Link } from 'react-router-dom'

import { avisaTopeCero, describirTope } from '../../../domain/identidad/topes'
import { enlaceDeUsuariosConTopePropio, textoDeTopesPorRol } from '../../../domain/identidad/usuarios'
import type { RolConTopeYPermisos } from '../../../features/descuentos/api'
import { PermisoRequeridoDescuentosError } from '../../../features/descuentos/errores'
import { useRolesConTope } from '../../../features/descuentos/hooks'
import { DescuentosSinPermiso, SIN_PERMISO_DE_TOPES } from './DescuentosSinPermiso'
import { TopeDialogo } from './TopeDialogo'

const TITULO = 'Topes por rol'
const AVISO_TOPE_CERO =
  'Con tope 0 %, si el rol tiene el permiso de descuento manual, necesita autorización para cualquier descuento manual.'

/**
 * Topes de descuento manual por rol (change 16, tarea 15.4, gobernanza crítica D13; spec
 * `administracion-de-descuentos`; DSC-06, `01` §19). Lista los roles de la organización con su
 * tope como porcentaje ("Sin tope" en 100 %) y permite cambiarlo, con confirmación, a quien tiene
 * `ADMIN_USUARIOS`. Solo cambia el tope: no toca permisos ni el tope propio de ningún usuario.
 * Un rol con tope 0 % y el permiso de descuento manual avisa que necesita autorización para cualquier descuento manual.
 */
export function TopesPorRolScreen() {
  const roles = useRolesConTope()
  const [editando, setEditando] = useState<RolConTopeYPermisos | null>(null)

  if (roles.isError) {
    if (roles.error instanceof PermisoRequeridoDescuentosError) {
      return <DescuentosSinPermiso titulo={TITULO} mensaje={SIN_PERMISO_DE_TOPES} />
    }
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo={TITULO} />
        <Alert>No se pudieron obtener los roles.</Alert>
      </main>
    )
  }

  const columnas: ColumnaTabla<RolConTopeYPermisos>[] = [
    {
      clave: 'rol',
      encabezado: 'Rol',
      render: (r) => (
        <div className="flex items-center gap-2">
          <span className="font-medium text-primary">{r.nombre}</span>
          {!r.activo && <Badge variante="negativo">De baja</Badge>}
        </div>
      ),
    },
    {
      clave: 'tope',
      encabezado: 'Tope de descuento manual',
      render: (r) => (
        <div className="flex flex-col">
          <span>{describirTope(r.tope_descuento)}</span>
          {avisaTopeCero(r) && <span className="text-primary/70">{AVISO_TOPE_CERO}</span>}
        </div>
      ),
    },
    {
      clave: 'topes-propios',
      encabezado: 'Usuarios con tope propio',
      render: (r) => {
        const texto = textoDeTopesPorRol(r.usuarios_con_tope_propio, r.usuarios_con_tope_propio_inactivos)
        return r.usuarios_con_tope_propio > 0 ? (
          <Link to={enlaceDeUsuariosConTopePropio(r.id)} className="text-primary hover:underline">
            {texto}
          </Link>
        ) : (
          <span>{texto}</span>
        )
      },
    },
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      render: (r) => (
        <Boton variante="secundario" aria-label={`Definir tope de ${r.nombre}`} onClick={() => setEditando(r)}>
          Definir tope
        </Boton>
      ),
    },
  ]

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} />
      <p className="text-sm text-primary/70">
        El tope es el mayor descuento manual que el rol puede dar sin autorización. Sin tope (100 %) no necesita pedirla.
        Este cambio no modifica los permisos del rol ni el tope propio de ningún usuario.
      </p>
      {roles.isPending && <p>Cargando…</p>}
      {roles.isSuccess && roles.data.length === 0 && <p className="text-sm text-primary/70">No hay roles.</p>}
      {roles.isSuccess && roles.data.length > 0 && (
        <Card>
          <Tabla filas={roles.data} columnas={columnas} obtenerClave={(r) => r.id} etiqueta={TITULO} />
        </Card>
      )}
      {editando && <TopeDialogo key={editando.id} rol={editando} onCerrar={() => setEditando(null)} />}
    </main>
  )
}

export default TopesPorRolScreen
