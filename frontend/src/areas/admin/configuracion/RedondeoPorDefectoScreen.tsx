import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import {
  esquemaRedondeoPorDefecto,
  type DatosDeRedondeo,
  type DatosDeRedondeoEntrada,
} from '../../../domain/configuracion/catalogos'
import { DIRECCIONES_REDONDEO, ETIQUETA_DE_DIRECCION } from '../../../domain/precios/listaSchema'
import type { RedondeoPorDefecto } from '../../../features/configuracion/api'
import { useDefinirRedondeoPorDefecto, useRedondeoPorDefecto } from '../../../features/configuracion/useRedondeoPorDefecto'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { AVISO_SIN_CONEXION, describirErrorDeRedondeo, estaSinConexion } from './erroresDeCatalogos'

const TITULO = 'Redondeo por defecto'
const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

function SinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} />
      <p className="text-sm text-primary/70">No tenés permiso para cambiar el redondeo por defecto.</p>
    </main>
  )
}

/**
 * Redondeo por defecto de la organización (change 20c, tarea 7.4; spec `parametros-de-organizacion`;
 * PRC-01, PRC-14, INV-03, ADR-061): el múltiplo y la dirección que trae cargado el formulario de una
 * lista nueva. Solo con `ADMIN_CONFIGURACION` (ADR-027). "Quitar" lo deja sin definir. No toca las
 * listas existentes. La misma validación que el formulario de lista; el servidor valida igual.
 */
export function RedondeoPorDefectoScreen() {
  return (
    <SiTienePermiso permiso="ADMIN_CONFIGURACION" fallback={<SinPermiso />}>
      <Contenido />
    </SiTienePermiso>
  )
}

function Contenido() {
  const redondeo = useRedondeoPorDefecto()
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} />
      <p className="text-sm text-primary/70">
        Es el redondeo que aparece cargado cuando creás una lista de precios nueva. Cambiarlo no modifica las listas que ya
        existen.
      </p>
      {redondeo.isPending && <p>Cargando…</p>}
      {redondeo.isError && <Alert>No se pudo obtener el redondeo por defecto.</Alert>}
      {redondeo.isSuccess && <Formulario actual={redondeo.data} />}
    </main>
  )
}

function Formulario({ actual }: { actual: RedondeoPorDefecto }) {
  const definir = useDefinirRedondeoPorDefecto()
  const [aviso, setAviso] = useState<string | null>(null)
  const definido = actual.multiplo !== null && actual.direccion !== null
  const {
    register,
    handleSubmit,
    setError,
    clearErrors,
    control,
    formState: { errors },
  } = useForm<DatosDeRedondeoEntrada, unknown, DatosDeRedondeo>({
    resolver: zodResolver(esquemaRedondeoPorDefecto),
    values: {
      redondeo_multiplo: actual.multiplo ?? '',
      redondeo_direccion: (actual.direccion ?? '') as DatosDeRedondeoEntrada['redondeo_direccion'],
    },
  })
  const multiplo = useWatch({ control, name: 'redondeo_multiplo' })
  const direccion = useWatch({ control, name: 'redondeo_direccion' })
  const operationId = useOperationIdDeEnvio({ multiplo: multiplo.trim(), direccion })
  const operationIdDeQuitar = useOperationIdDeEnvio({ quitar: true, desde: actual })

  const enviar = async (cuerpo: { multiplo: string | null; direccion: string | null }, id: () => string, completar: () => void, aviso: string) => {
    setAviso(null)
    if (estaSinConexion()) {
      setError('root', { message: AVISO_SIN_CONEXION })
      return
    }
    try {
      await definir.mutateAsync({ ...cuerpo, operationId: id() })
      completar()
      clearErrors('root')
      setAviso(aviso)
    } catch (falla) {
      setError('root', { message: describirErrorDeRedondeo(falla) })
    }
  }

  const guardar = handleSubmit((datos) =>
    enviar(
      { multiplo: datos.redondeo_multiplo, direccion: datos.redondeo_direccion },
      operationId.obtener,
      operationId.completar,
      'Se guardó el redondeo por defecto.',
    ),
  )
  const quitar = () =>
    enviar(
      { multiplo: null, direccion: null },
      operationIdDeQuitar.obtener,
      operationIdDeQuitar.completar,
      'Se quitó el redondeo por defecto: la lista nueva empieza con el redondeo vacío.',
    )

  return (
    <Card>
      <form onSubmit={(evento) => void guardar(evento)} noValidate className="flex flex-col gap-4">
        <p className="text-sm text-primary">
          {definido ? 'Redondeo definido.' : 'Sin definir: la lista nueva empieza con el redondeo vacío.'}
        </p>
        <Campo
          id="redondeo-multiplo"
          etiqueta="Múltiplo de redondeo"
          ayuda="configuracion.redondeoPorDefecto"
          error={errors.redondeo_multiplo?.message}
        >
          <input id="redondeo-multiplo" inputMode="decimal" className={CLASE_CONTROL} {...register('redondeo_multiplo')} />
        </Campo>
        <Campo id="redondeo-direccion" etiqueta="Dirección del redondeo" error={errors.redondeo_direccion?.message}>
          <select id="redondeo-direccion" className={CLASE_CONTROL} {...register('redondeo_direccion')}>
            <option value="">Elegí una dirección</option>
            {DIRECCIONES_REDONDEO.map((codigo) => (
              <option key={codigo} value={codigo}>
                {ETIQUETA_DE_DIRECCION[codigo]}
              </option>
            ))}
          </select>
        </Campo>
        {errors.root?.message && <Alert>{errors.root.message}</Alert>}
        {aviso && (
          <p role="status" className="text-sm text-primary">
            {aviso}
          </p>
        )}
        <div className="flex gap-2">
          <Boton type="submit" disabled={definir.isPending}>
            Guardar
          </Boton>
          {definido && (
            <Boton variante="secundario" disabled={definir.isPending} onClick={() => void quitar()}>
              Quitar
            </Boton>
          )}
        </div>
      </form>
    </Card>
  )
}

export default RedondeoPorDefectoScreen
