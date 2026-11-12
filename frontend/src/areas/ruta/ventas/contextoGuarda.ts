import { createContext, useContext } from 'react'

/**
 * Contexto de la guarda del carrito (change 22a, `design.md` D12; `02` §13.5). La pantalla de
 * venta avisa con `marcar(true)` mientras tiene alguna línea o una confirmación en curso y con
 * `marcar(false)` al confirmar, descartar o desmontarse. Lo leen el aviso de versión nueva (no
 * ofrece "Actualizar") y el menú de `/ruta` (pregunta antes de salir). Sin proveedor, nada está
 * ocupado.
 */
export interface GuardaDelCarrito {
  ocupado: boolean
  marcar: (ocupado: boolean) => void
}

const SIN_GUARDA: GuardaDelCarrito = { ocupado: false, marcar: () => undefined }

export const ContextoGuarda = createContext<GuardaDelCarrito>(SIN_GUARDA)

export function useGuardaDelCarrito(): GuardaDelCarrito {
  return useContext(ContextoGuarda)
}
