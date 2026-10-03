import { describe, expect, it } from 'vitest'

import { primeraSeccionPermitida, SECCIONES, seccionesPermitidas } from '../../../../src/features/identidad/secciones'

const conPermisos = (...permisos: string[]) => (permiso: string) => permisos.includes(permiso)

describe('sección "Compras" del menú (change 11, D14)', () => {
  it('está declarada con /admin/compras', () => {
    const seccion = SECCIONES.find((s) => s.ruta === '/admin/compras')
    expect(seccion?.etiqueta).toBe('Compras')
  })

  it.each([['REGISTRAR_COMPRA'], ['ANULAR_COMPRA'], ['REGISTRAR_COMPRA', 'ANULAR_COMPRA']])(
    'se ofrece con %s',
    (...permisos) => {
      const etiquetas = seccionesPermitidas(conPermisos(...permisos)).map((s) => s.etiqueta)
      expect(etiquetas).toContain('Compras')
    },
  )

  it('no se ofrece sin REGISTRAR_COMPRA ni ANULAR_COMPRA', () => {
    const etiquetas = seccionesPermitidas(conPermisos('GESTIONAR_CATALOGO', 'GESTIONAR_PROVEEDORES')).map((s) => s.etiqueta)
    expect(etiquetas).not.toContain('Compras')
  })

  it('un usuario con solo ANULAR_COMPRA aterriza en Compras', () => {
    expect(primeraSeccionPermitida(conPermisos('ANULAR_COMPRA'))?.ruta).toBe('/admin/compras')
  })
})

describe('sección "Configuración" del menú (change 11b, D7, tarea 7.4)', () => {
  it('está declarada con /admin/configuracion', () => {
    expect(SECCIONES.find((s) => s.ruta === '/admin/configuracion')?.etiqueta).toBe('Configuración')
  })

  it('se ofrece con ADMIN_CONFIGURACION', () => {
    expect(seccionesPermitidas(conPermisos('ADMIN_CONFIGURACION')).map((s) => s.etiqueta)).toContain('Configuración')
  })

  it('no se ofrece sin ADMIN_CONFIGURACION', () => {
    expect(
      seccionesPermitidas(conPermisos('GESTIONAR_CATALOGO', 'REGISTRAR_COMPRA')).map((s) => s.etiqueta),
    ).not.toContain('Configuración')
  })
})
