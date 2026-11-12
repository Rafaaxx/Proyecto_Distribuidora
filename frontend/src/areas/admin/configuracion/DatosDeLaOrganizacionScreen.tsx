import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import { esquemaDatosOrganizacion, type DatosDeOrganizacion } from '../../../domain/configuracion/datosOrganizacion'
import type { OrganizacionDatos } from '../../../features/configuracion/api'
import { ErrorDeConfiguracion } from '../../../features/configuracion/errores'
import {
  useConfigurarDatosOrganizacion,
  useDatosOrganizacion,
} from '../../../features/configuracion/useDatosOrganizacion'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'

const TITULO = 'Datos de la organización'
const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'
const MENSAJE_DE_RED = 'No se pudo guardar. Podés reintentar: se reenvía la misma operación.'
const CODIGO_CUIT_INVALIDO = 'CUIT_INVALIDO'
const CODIGO_NOMBRE_INVALIDO = 'NOMBRE_DE_ORGANIZACION_INVALIDO'

interface FormularioDeOrganizacion {
  nombre: string
  cuit: string
}

function SinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} />
      <p className="text-sm text-primary/70">No tenés permiso para cambiar la configuración de la empresa.</p>
    </main>
  )
}

/**
 * Nombre y CUIT de la organización (change 20, D15; spec `parametros-de-organizacion`; VTA-13,
 * AUD-01, SEG-06). Solo con `ADMIN_CONFIGURACION` (ADR-027: sin el permiso no se monta ni pide
 * nada). El nombre se valida acá solo como ayuda (vacío); el CUIT y el largo los valida el servidor.
 * Lo que se guarda se imprime en el encabezado de la nota de venta.
 */
export function DatosDeLaOrganizacionScreen() {
  return (
    <SiTienePermiso permiso="ADMIN_CONFIGURACION" fallback={<SinPermiso />}>
      <Contenido />
    </SiTienePermiso>
  )
}

function Contenido() {
  const datos = useDatosOrganizacion()
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} />
      {datos.isPending && <p className="text-sm text-primary/70">Cargando…</p>}
      {datos.isError && <Alert>No se pudo obtener los datos de la organización.</Alert>}
      {datos.isSuccess && <Bloque actual={datos.data} />}
    </main>
  )
}

function Bloque({ actual }: { actual: OrganizacionDatos }) {
  const [guardado, setGuardado] = useState(false)
  const configurar = useConfigurarDatosOrganizacion()
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isDirty },
  } = useForm<FormularioDeOrganizacion, unknown, DatosDeOrganizacion>({
    resolver: zodResolver(esquemaDatosOrganizacion),
    defaultValues: { nombre: actual.nombre, cuit: actual.cuit ?? '' },
  })

  const alEnviar = handleSubmit(async (formulario) => {
    setGuardado(false)
    const cuit = formulario.cuit.trim()
    try {
      const guardada = await configurar.mutateAsync({ nombre: formulario.nombre, cuit: cuit === '' ? null : cuit })
      reset({ nombre: guardada.nombre, cuit: guardada.cuit ?? '' })
      setGuardado(true)
    } catch (falla) {
      if (falla instanceof ErrorDeConfiguracion && falla.codigo === CODIGO_CUIT_INVALIDO) {
        setError('cuit', { message: falla.message })
      } else if (falla instanceof ErrorDeConfiguracion && falla.codigo === CODIGO_NOMBRE_INVALIDO) {
        setError('nombre', { message: falla.message })
      } else {
        setError('root', { message: falla instanceof ErrorDeConfiguracion ? falla.message : MENSAJE_DE_RED })
      }
    }
  })

  return (
    <Card className="flex flex-col gap-3">
      <form onSubmit={(evento) => void alEnviar(evento)} noValidate className="flex flex-col gap-3" data-testid="bloque-datos-organizacion">
        <div data-testid="campo-nombre">
          <Campo id="organizacion-nombre" etiqueta="Nombre" error={errors.nombre?.message}>
            <input id="organizacion-nombre" className={`${CLASE_CONTROL} w-full max-w-md`} {...register('nombre')} />
          </Campo>
        </div>
        <div data-testid="campo-cuit">
          <Campo id="organizacion-cuit" etiqueta="CUIT" error={errors.cuit?.message}>
            <input id="organizacion-cuit" className={`${CLASE_CONTROL} w-full max-w-xs`} {...register('cuit')} />
          </Campo>
        </div>
        {errors.root?.message && <Alert>{errors.root.message}</Alert>}
        {guardado && !errors.root && !errors.nombre && !errors.cuit && (
          <p role="status" className="text-sm text-primary">
            Se guardaron los datos de la organización.
          </p>
        )}
        <div>
          <Boton type="submit" disabled={!isDirty || configurar.isPending}>
            Guardar datos de la organización
          </Boton>
        </div>
      </form>
    </Card>
  )
}

export default DatosDeLaOrganizacionScreen
