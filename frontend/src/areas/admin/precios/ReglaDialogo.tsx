import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import { Campo } from '../../../components/ui/Field'
import { formulaDesdePorcentaje, etiquetaDeAlcance, etiquetaDeTipoDeMargen } from '../../../domain/precios/presentacion'
import {
  ALCANCES,
  TIPOS_DE_MARGEN,
  esquemaRegla,
  fraccionDesdePorcentaje,
  porcentajeDesdeFraccion,
  type DatosRegla,
  type DatosReglaEntrada,
} from '../../../domain/precios/reglaSchema'
import type { Regla } from '../../../features/precios/api'
import { useCrearRegla, useModificarRegla } from '../../../features/precios/hooks'
import { campoDeReglaParaCodigo } from '../../../features/precios/mapaErrorACampo'
import { describirError } from './errores'
import { SelectorDeEntidad } from './SelectorDeEntidad'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

interface ReglaDialogoProps {
  listaId: string
  /** Sin regla es el alta; con regla se editan tipo, valor y actividad (el alcance no cambia). */
  regla?: Regla
  abierto: boolean
  onCerrar: () => void
}

/**
 * Alta y edición de una regla de margen (change 13, tarea 13.1; PRC-12, PRC-13, D8). La persona
 * escribe un porcentaje; el comando lleva la fracción de seis decimales como string. La fórmula
 * aplicada se ve mientras se escribe. `REGLA_DUPLICADA` y `ALCANCE_INVALIDO` se muestran junto
 * al alcance y el formulario conserva lo cargado (TR-10).
 */
export function ReglaDialogo({ listaId, regla, abierto, onCerrar }: ReglaDialogoProps) {
  if (!abierto) return null
  return <ReglaFormulario key={regla?.id ?? 'nueva'} listaId={listaId} regla={regla} onCerrar={onCerrar} />
}

function ReglaFormulario({ listaId, regla, onCerrar }: Omit<ReglaDialogoProps, 'abierto'>) {
  const esEdicion = regla !== undefined
  const crear = useCrearRegla()
  const modificar = useModificarRegla()
  const [activa, setActiva] = useState(regla?.activo ?? true)
  const {
    register,
    handleSubmit,
    setError,
    setValue,
    control,
    formState: { errors },
  } = useForm<DatosReglaEntrada, unknown, DatosRegla>({
    resolver: zodResolver(esquemaRegla),
    defaultValues: {
      tipo: (regla?.tipo ?? 'MARKUP') as DatosReglaEntrada['tipo'],
      porcentaje: regla ? porcentajeDesdeFraccion(regla.valor) : '',
      alcance_tipo: (regla?.alcance_tipo ?? 'LISTA') as DatosReglaEntrada['alcance_tipo'],
      alcance_id: regla?.alcance_id ?? '',
    },
  })
  const [tipo, porcentaje, alcanceTipo] = useWatch({ control, name: ['tipo', 'porcentaje', 'alcance_tipo'] })
  const formula = formulaDesdePorcentaje(tipo, porcentaje)

  const alEnviar = handleSubmit(async (datos) => {
    const valor = fraccionDesdePorcentaje(datos.porcentaje)
    try {
      if (regla) {
        await modificar.mutateAsync({ listaId, reglaId: regla.id, tipo: datos.tipo, valor, activo: activa })
      } else {
        await crear.mutateAsync({
          listaId,
          tipo: datos.tipo,
          valor,
          alcance_tipo: datos.alcance_tipo,
          alcance_id: datos.alcance_tipo === 'LISTA' ? null : datos.alcance_id,
        })
      }
      onCerrar()
    } catch (error) {
      const { codigo, mensaje } = describirError(error)
      const campo = codigo === null ? null : campoDeReglaParaCodigo(codigo)
      setError(campo === 'porcentaje' ? 'porcentaje' : campo === 'alcance' ? 'alcance_tipo' : 'root', {
        message: mensaje,
      })
    }
  })

  return (
    <Dialogo abierto titulo={esEdicion ? 'Editar regla de margen' : 'Nueva regla de margen'} onCerrar={onCerrar}>
      <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
        <Campo id="regla-tipo" etiqueta="Tipo de margen" error={errors.tipo?.message}>
          <select id="regla-tipo" className={CLASE_CONTROL} {...register('tipo')}>
            {TIPOS_DE_MARGEN.map((valor) => (
              <option key={valor} value={valor}>
                {etiquetaDeTipoDeMargen(valor)}
              </option>
            ))}
          </select>
        </Campo>
        <Campo id="regla-porcentaje" etiqueta="Porcentaje" error={errors.porcentaje?.message}>
          <input id="regla-porcentaje" inputMode="decimal" className={CLASE_CONTROL} {...register('porcentaje')} />
        </Campo>
        {formula && <p className="text-sm text-primary/70">{formula}</p>}

        {esEdicion ? (
          <>
            <p className="text-sm text-primary/80">
              Se aplica a: {etiquetaDeAlcance(regla.alcance_tipo)}
              {regla.alcance_nombre ? ` · ${regla.alcance_nombre}` : ''}
            </p>
            <Campo id="regla-activa" etiqueta="Activa">
              <input
                id="regla-activa"
                type="checkbox"
                className="h-4 w-4 self-start"
                checked={activa}
                onChange={(evento) => setActiva(evento.target.checked)}
              />
            </Campo>
          </>
        ) : (
          <>
            <Campo id="regla-alcance" etiqueta="Se aplica a" error={errors.alcance_tipo?.message}>
              <select
                id="regla-alcance"
                className={CLASE_CONTROL}
                {...register('alcance_tipo', { onChange: () => setValue('alcance_id', '') })}
              >
                {ALCANCES.map((valor) => (
                  <option key={valor} value={valor}>
                    {etiquetaDeAlcance(valor)}
                  </option>
                ))}
              </select>
            </Campo>
            {alcanceTipo !== 'LISTA' && (
              <Campo id="regla-entidad" etiqueta="Entidad" error={errors.alcance_id?.message}>
                <SelectorDeEntidad alcance={alcanceTipo} id="regla-entidad" registro={register('alcance_id')} />
              </Campo>
            )}
          </>
        )}

        {errors.root?.message && <Alert>{errors.root.message}</Alert>}

        <div className="flex gap-2">
          <Boton type="submit" disabled={crear.isPending || modificar.isPending}>
            Guardar regla
          </Boton>
          <Boton type="button" variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
        </div>
      </form>
    </Dialogo>
  )
}
