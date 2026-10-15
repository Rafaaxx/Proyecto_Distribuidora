import { zodResolver } from '@hookform/resolvers/zod'
import { useMemo, useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import { etiquetaDeValorDeAccion, formularioDesdeRegla } from '../../../domain/descuentos/formulario'
import { etiquetaDeMedida } from '../../../domain/descuentos/presentacion'
import {
  esquemaReglaDescuento,
  type AlcanceDeFormulario,
  type DatosReglaDescuento,
  type DatosReglaDescuentoEntrada,
} from '../../../domain/descuentos/reglaSchema'
import { ACCIONES, MEDIDAS, OPERADORES } from '../../../domain/descuentos/tipos'
import type { ReglaDescuento } from '../../../features/descuentos/api'
import { ErrorDeApiDescuentos } from '../../../features/descuentos/errores'
import { useCrearReglaDescuento, useModificarReglaDescuento, useReglaDescuento } from '../../../features/descuentos/hooks'
import { campoDeReglaDeDescuentoParaCodigo, mensajeDeErrorDeDescuentos } from '../../../features/descuentos/mapaErrorACampo'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { AVISO_SIN_CONEXION, describirError, estaSinConexion } from './errores'
import { SelectorDeAlcances } from './SelectorDeAlcances'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'
const ETIQUETA_DE_OPERADOR: Record<string, string> = { GTE: 'Mayor o igual (≥)', GT: 'Mayor (>)' }
const ETIQUETA_DE_ACCION: Record<string, string> = { PORCENTAJE: 'Porcentaje', IMPORTE_FIJO: 'Importe fijo' }

const VALORES_DE_ALTA: DatosReglaDescuentoEntrada = {
  nombre: '',
  tipo: 'VOLUMEN_OPERACION',
  medida: 'CAJAS_EQUIVALENTES',
  operador: 'GTE',
  umbral: '',
  accion_tipo: 'PORCENTAJE',
  accion_valor: '',
  prioridad: '',
  acumulable: false,
  alcances: [],
  vigencia_desde: '',
  vigencia_hasta: '',
}

/**
 * Alta y edición de una regla de descuento (change 16, tarea 15.2; DSC-01 a DSC-04, TR-02, TR-10).
 * Sin `reglaId` en la ruta (`/admin/descuentos/nueva`) es el alta; con `reglaId`
 * (`/admin/descuentos/:reglaId/editar`), la edición de un borrador. La persona escribe el porcentaje
 * como porcentaje; el comando lleva la fracción como cadena. Las validaciones viven en
 * `domain/descuentos/reglaSchema.ts`; el servidor valida igual.
 */
export function ReglaFormScreen() {
  const { reglaId } = useParams<{ reglaId?: string }>()
  return reglaId ? <ReglaEdicion reglaId={reglaId} /> : <ReglaAlta />
}

function ReglaAlta() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Nueva regla de descuento" />
      <FormularioDeRegla
        valores={VALORES_DE_ALTA}
        nombresIniciales={{}}
        textoDelBoton="Guardar regla"
        rutaDeSalida="/admin/descuentos"
      />
    </main>
  )
}

function ReglaEdicion({ reglaId }: { reglaId: string }) {
  const regla = useReglaDescuento(reglaId)

  if (regla.isPending) {
    return (
      <main>
        <p>Cargando…</p>
      </main>
    )
  }
  if (regla.isError) {
    const noExiste = regla.error instanceof ErrorDeApiDescuentos && regla.error.estado === 404
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo="Regla de descuento" />
        <Alert>{noExiste ? 'No se encontró la regla.' : 'No se pudo obtener la regla.'}</Alert>
      </main>
    )
  }

  const detalle = regla.data
  const rutaDelDetalle = `/admin/descuentos/${reglaId}`
  if (detalle.estado !== 'BORRADOR') {
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo={detalle.nombre} />
        <p className="text-sm text-primary/80">
          Solo se edita una regla en borrador. Esta regla está {detalle.estado.toLowerCase()}: para cambiarla, pausala y
          creá otra, o poné fin a su vigencia.
        </p>
        <Link to={rutaDelDetalle} className="text-sm text-primary/70 hover:text-primary hover:underline">
          Volver al detalle
        </Link>
      </main>
    )
  }
  return <EdicionDeBorrador regla={detalle} rutaDelDetalle={rutaDelDetalle} />
}

function EdicionDeBorrador({ regla, rutaDelDetalle }: { regla: ReglaDescuento; rutaDelDetalle: string }) {
  const valores = useMemo(() => formularioDesdeRegla(regla), [regla])
  const nombres = useMemo(
    () => Object.fromEntries(regla.alcances.map((a) => [`${a.tipo}:${a.entidad_id}`, a.nombre])),
    [regla],
  )
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={regla.nombre} />
      <FormularioDeRegla
        valores={valores}
        nombresIniciales={nombres}
        reglaId={regla.id}
        textoDelBoton="Guardar cambios"
        rutaDeSalida={rutaDelDetalle}
      />
    </main>
  )
}

interface FormularioDeReglaProps {
  valores: DatosReglaDescuentoEntrada
  nombresIniciales: Record<string, string>
  /** Con `reglaId` se reemplaza ese borrador; sin él se crea una regla. */
  reglaId?: string
  textoDelBoton: string
  rutaDeSalida: string
}

function FormularioDeRegla({ valores, nombresIniciales, reglaId, textoDelBoton, rutaDeSalida }: FormularioDeReglaProps) {
  const navigate = useNavigate()
  const crear = useCrearReglaDescuento()
  const modificar = useModificarReglaDescuento()
  const [nombres, setNombres] = useState<Record<string, string>>(nombresIniciales)
  const {
    register,
    handleSubmit,
    setError,
    setValue,
    clearErrors,
    control,
    formState: { errors },
  } = useForm<DatosReglaDescuentoEntrada, unknown, DatosReglaDescuento>({
    resolver: zodResolver(esquemaReglaDescuento),
    defaultValues: valores,
  })
  const contenido = useWatch({ control })
  const [tipo, accionTipo, alcances] = useWatch({ control, name: ['tipo', 'accion_tipo', 'alcances'] })
  const operationId = useOperationIdDeEnvio({ reglaId: reglaId ?? null, contenido })

  const alEnviar = handleSubmit(async (datos) => {
    if (estaSinConexion()) {
      setError('root', { message: AVISO_SIN_CONEXION })
      return
    }
    try {
      const guardada = reglaId
        ? await modificar.mutateAsync({ reglaId, ...datos, operationId: operationId.obtener() })
        : await crear.mutateAsync({ ...datos, operationId: operationId.obtener() })
      operationId.completar()
      navigate(`/admin/descuentos/${guardada.id}`)
    } catch (error) {
      const { codigo, mensaje } = describirError(error)
      const campo = codigo === null ? null : campoDeReglaDeDescuentoParaCodigo(codigo)
      setError(campo ?? 'root', { message: mensajeDeErrorDeDescuentos(codigo, mensaje) })
    }
  })

  return (
    <Card>
      <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
        <Campo id="nombre" etiqueta="Nombre" error={errors.nombre?.message}>
          <input id="nombre" className={CLASE_CONTROL} {...register('nombre')} />
        </Campo>

        <Campo id="tipo" etiqueta="Alcance de la regla" error={errors.tipo?.message}>
          <select
            id="tipo"
            className={CLASE_CONTROL}
            {...register('tipo', {
              onChange: (evento: { target: { value: string } }) => {
                if (evento.target.value === 'VOLUMEN_OPERACION') {
                  setValue('alcances', [])
                  clearErrors('alcances')
                }
              },
            })}
          >
            <option value="VOLUMEN_OPERACION">Sobre toda la venta</option>
            <option value="VOLUMEN_ALCANCE">Sobre productos, categorías o marcas</option>
          </select>
        </Campo>
        {tipo === 'VOLUMEN_ALCANCE' && (
          <SelectorDeAlcances
            alcances={alcances}
            nombres={nombres}
            error={errors.alcances?.message}
            onCambiar={(nuevos: AlcanceDeFormulario[], nuevosNombres) => {
              setNombres(nuevosNombres)
              setValue('alcances', nuevos, { shouldDirty: true })
              clearErrors('alcances')
            }}
          />
        )}

        <div className="grid gap-4 sm:grid-cols-3">
          <Campo id="medida" etiqueta="Medida" error={errors.medida?.message}>
            <select id="medida" className={CLASE_CONTROL} {...register('medida')}>
              {MEDIDAS.map((valor) => (
                <option key={valor} value={valor}>
                  {etiquetaDeMedida(valor)}
                </option>
              ))}
            </select>
          </Campo>
          <Campo id="operador" etiqueta="Operador" error={errors.operador?.message}>
            <select id="operador" className={CLASE_CONTROL} {...register('operador')}>
              {OPERADORES.map((valor) => (
                <option key={valor} value={valor}>
                  {ETIQUETA_DE_OPERADOR[valor]}
                </option>
              ))}
            </select>
          </Campo>
          <Campo id="umbral" etiqueta="Umbral" error={errors.umbral?.message}>
            <input id="umbral" inputMode="decimal" className={CLASE_CONTROL} {...register('umbral')} />
          </Campo>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Campo id="accion_tipo" etiqueta="Acción" error={errors.accion_tipo?.message}>
            <select id="accion_tipo" className={CLASE_CONTROL} {...register('accion_tipo')}>
              {ACCIONES.map((valor) => (
                <option key={valor} value={valor}>
                  {ETIQUETA_DE_ACCION[valor]}
                </option>
              ))}
            </select>
          </Campo>
          <Campo id="accion_valor" etiqueta={etiquetaDeValorDeAccion(accionTipo)} error={errors.accion_valor?.message}>
            <input id="accion_valor" inputMode="decimal" className={CLASE_CONTROL} {...register('accion_valor')} />
          </Campo>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Campo id="prioridad" etiqueta="Prioridad" error={errors.prioridad?.message}>
            <input id="prioridad" inputMode="numeric" className={CLASE_CONTROL} {...register('prioridad')} />
          </Campo>
          <Campo id="acumulable" etiqueta="Acumulable">
            <input id="acumulable" type="checkbox" className="h-4 w-4 self-start" {...register('acumulable')} />
          </Campo>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Campo id="vigencia_desde" etiqueta="Vigencia desde (opcional)" error={errors.vigencia_desde?.message}>
            <input id="vigencia_desde" type="datetime-local" className={CLASE_CONTROL} {...register('vigencia_desde')} />
          </Campo>
          <Campo id="vigencia_hasta" etiqueta="Vigencia hasta (opcional)" error={errors.vigencia_hasta?.message}>
            <input id="vigencia_hasta" type="datetime-local" className={CLASE_CONTROL} {...register('vigencia_hasta')} />
          </Campo>
        </div>

        {errors.root?.message && <Alert>{errors.root.message}</Alert>}
        <div className="flex gap-2">
          <Boton type="submit" disabled={crear.isPending || modificar.isPending}>
            {textoDelBoton}
          </Boton>
          <Link to={rutaDeSalida} className="self-center text-sm text-primary/70 hover:text-primary">
            Cancelar
          </Link>
        </div>
      </form>
    </Card>
  )
}

export default ReglaFormScreen
