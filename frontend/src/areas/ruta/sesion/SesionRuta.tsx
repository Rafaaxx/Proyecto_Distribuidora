import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { renovarSesion } from '../../../lib/api/httpClient'
import { definirPin, desbloquearConPin, type ResultadoDesbloqueo } from '../../../lib/sesionLocal/pin'
import { LoginRutaScreen, type MotivoDeLogin } from '../auth/LoginRutaScreen'
import { ContextoSesion, type SesionRutaActiva } from './contextoSesion'
import { sincronizarAlEntrar, type ResultadoEntrada } from './entrada'
import { DefinirPinScreen, PedirPinScreen } from './PantallasDePin'
import { estadoInicialDeRuta, registrarUsuarioTrasLogin } from './arranque'

/**
 * Máquina de estados de `/ruta` (change 21, D11 a D16; SEG-03, ADR-017):
 * cargando → login → definir PIN → entrando (bootstrap pendiente) → activa; el arranque o la
 * recarga con sesión local piden el PIN. NO hay regla de segundo plano (D14 = B): volver de
 * segundo plano no cambia el estado; solo un arranque nuevo vuelve a pedir el PIN.
 */
type Estado =
  | { fase: 'cargando' }
  | { fase: 'login'; motivo?: MotivoDeLogin }
  | { fase: 'definir_pin' }
  | { fase: 'pedir_pin' }
  | { fase: 'entrando' }
  | { fase: 'activa'; entrada: ResultadoEntrada }

function mensajeDeFallo(r: ResultadoDesbloqueo): string {
  if (r.tipo !== 'incorrecto') return 'No se pudo comprobar el PIN.'
  return r.restantes === 1 ? 'PIN incorrecto. Te queda 1 intento.' : `PIN incorrecto. Te quedan ${r.restantes} intentos.`
}

export function SesionRuta({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<Estado>({ fase: 'cargando' })

  useEffect(() => {
    let vigente = true
    void estadoInicialDeRuta().then((inicial) => {
      if (vigente) setEstado({ fase: inicial === 'pedir_pin' ? 'pedir_pin' : 'login' })
    })
    return () => {
      vigente = false
    }
  }, [])

  /** Consulta la jornada y baja el bootstrap si corresponde; pasa a `activa` o al login. */
  const entrar = useCallback(async () => {
    setEstado({ fase: 'entrando' })
    const entrada = await sincronizarAlEntrar()
    setEstado(
      entrada.tipo === 'sesion_vencida' ? { fase: 'login', motivo: 'sesion_vencida' } : { fase: 'activa', entrada },
    )
  }, [])

  const alIniciarSesion = useCallback(async () => {
    const { hayPin } = await registrarUsuarioTrasLogin()
    if (hayPin) await entrar()
    else setEstado({ fase: 'definir_pin' })
  }, [entrar])

  const alDefinirPin = useCallback(
    async (pin: string, confirmacion: string): Promise<string | null> => {
      const r = await definirPin(pin, confirmacion)
      if (!r.ok) return r.motivo
      await entrar()
      return null
    },
    [entrar],
  )

  const alDesbloquear = useCallback(
    async (pin: string): Promise<string | null> => {
      const r = await desbloquearConPin(pin)
      if (r.tipo === 'bloqueado' || r.tipo === 'sin_pin') {
        setEstado({ fase: 'login', motivo: 'bloqueado' })
        return null
      }
      if (r.tipo === 'incorrecto') return mensajeDeFallo(r)

      // D14: con señal se renueva el access token; sin señal se desbloquea sin tocar la red.
      if (!navigator.onLine) {
        setEstado({ fase: 'activa', entrada: { tipo: 'sin_red' } })
        return null
      }
      const renovacion = await renovarSesion()
      if (renovacion === 'rechazada') {
        setEstado({ fase: 'login', motivo: 'sesion_vencida' })
      } else if (renovacion === 'sin_red') {
        setEstado({ fase: 'activa', entrada: { tipo: 'sin_red' } })
      } else {
        await entrar()
      }
      return null
    },
    [entrar],
  )

  const alCerrarSesion = useCallback(() => setEstado({ fase: 'login', motivo: 'cerrada' }), [])
  const alBloquearse = useCallback(() => setEstado({ fase: 'login', motivo: 'bloqueado' }), [])

  const activa = estado.fase === 'activa' ? estado.entrada : null
  const valor = useMemo<SesionRutaActiva | null>(
    () => (activa === null ? null : { entrada: activa, alCerrarSesion, alBloquearse, reintentarEntrada: entrar }),
    [activa, alCerrarSesion, alBloquearse, entrar],
  )

  switch (estado.fase) {
    case 'cargando':
    case 'entrando':
      return (
        <main className="flex min-h-dvh items-center justify-center bg-surface-muted p-4">
          <p role="status" className="text-sm text-primary">
            {estado.fase === 'entrando' ? 'Preparando tus datos…' : 'Cargando…'}
          </p>
        </main>
      )
    case 'login':
      return <LoginRutaScreen motivo={estado.motivo} onIniciada={() => void alIniciarSesion()} />
    case 'definir_pin':
      return <DefinirPinScreen onDefinir={alDefinirPin} />
    case 'pedir_pin':
      return <PedirPinScreen onDesbloquear={alDesbloquear} />
    case 'activa':
      return <ContextoSesion.Provider value={valor}>{children}</ContextoSesion.Provider>
  }
}
