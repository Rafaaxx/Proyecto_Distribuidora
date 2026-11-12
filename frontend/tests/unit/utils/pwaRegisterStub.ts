/** Sustituto de `virtual:pwa-register/react` para las pruebas (el módulo real solo existe en el build). */
export function useRegisterSW() {
  return {
    needRefresh: [false, () => undefined] as const,
    offlineReady: [false, () => undefined] as const,
    updateServiceWorker: () => Promise.resolve(),
  }
}
