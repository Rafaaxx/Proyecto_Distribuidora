/**
 * Reglas de la pantalla "Roles y permisos" (change 17b, `design.md` D9; `01` §19, ADR-011,
 * ADR-053). Dominio puro: el componente solo dibuja lo que esto calcula.
 */

export interface PermisoDelCatalogo {
  codigo: string
  descripcion: string
  modulo: string
}

export interface GrupoDePermisos {
  modulo: string
  etiqueta: string
  permisos: PermisoDelCatalogo[]
}

/** Permisos que permiten autorizar excepciones con PIN (ADR-011). */
export const PERMISOS_DE_AUTORIZACION: readonly string[] = [
  'AUTORIZAR_DESCUENTO',
  'SUPERAR_CREDITO',
  'VENDER_CLIENTE_SUSPENDIDO',
  'USAR_LISTA_ANTERIOR',
]

/** Módulos cuyas funciones todavía no existen en la aplicación (facturación y reportes; ventas existe desde el change 18a). */
const MODULOS_QUE_LLEGAN_MAS_ADELANTE: readonly string[] = ['facturacion', 'reportes']

const ETIQUETAS_DE_MODULO: Record<string, string> = {
  identidad: 'Usuarios y organización',
  importacion: 'Importación',
  catalogo: 'Catálogo',
  clientes: 'Clientes',
  proveedores: 'Proveedores',
  costeo: 'Costos',
  precios: 'Listas de precios',
  descuentos: 'Descuentos',
  stock: 'Stock',
  ventas: 'Ventas',
  cobranzas: 'Cobranzas',
  sync: 'Sincronización',
  reportes: 'Reportes',
  auditoria: 'Auditoría',
  facturacion: 'Facturación',
}

export function etiquetaDeModulo(modulo: string): string {
  const conocida = ETIQUETAS_DE_MODULO[modulo]
  if (conocida) return conocida
  const texto = modulo.replaceAll('_', ' ')
  return texto.charAt(0).toUpperCase() + texto.slice(1)
}

export function llegaMasAdelante(modulo: string): boolean {
  return MODULOS_QUE_LLEGAN_MAS_ADELANTE.includes(modulo)
}

/** Agrupa por módulo en el orden en que cada módulo aparece por primera vez en el catálogo. */
export function agruparPorModulo(catalogo: readonly PermisoDelCatalogo[]): GrupoDePermisos[] {
  const grupos = new Map<string, GrupoDePermisos>()
  for (const permiso of catalogo) {
    const grupo = grupos.get(permiso.modulo) ?? {
      modulo: permiso.modulo,
      etiqueta: etiquetaDeModulo(permiso.modulo),
      permisos: [],
    }
    grupo.permisos.push(permiso)
    grupos.set(permiso.modulo, grupo)
  }
  return [...grupos.values()]
}

export function rolConfiereAutorizacion(permisos: readonly string[]): boolean {
  return permisos.some((codigo) => PERMISOS_DE_AUTORIZACION.includes(codigo))
}

/** Tenía algún permiso de autorización y se queda sin ninguno: se borra el PIN de sus usuarios. */
export function perdeLaAutorizacion(actuales: readonly string[], nuevos: readonly string[]): boolean {
  return rolConfiereAutorizacion(actuales) && !rolConfiereAutorizacion(nuevos)
}

function enOrdenDeCatalogo(codigos: readonly string[], catalogo: readonly PermisoDelCatalogo[]): string[] {
  const orden = new Map(catalogo.map((permiso, indice) => [permiso.codigo, indice]))
  const fuera = catalogo.length
  return [...codigos].sort((a, b) => (orden.get(a) ?? fuera) - (orden.get(b) ?? fuera))
}

/** Qué agrega y qué quita el cambio, en el orden del catálogo (un código desconocido va al final). */
export function diferenciaDePermisos(
  actuales: readonly string[],
  nuevos: readonly string[],
  catalogo: readonly PermisoDelCatalogo[],
): { agrega: string[]; quita: string[] } {
  return {
    agrega: enOrdenDeCatalogo(
      nuevos.filter((codigo) => !actuales.includes(codigo)),
      catalogo,
    ),
    quita: enOrdenDeCatalogo(
      actuales.filter((codigo) => !nuevos.includes(codigo)),
      catalogo,
    ),
  }
}

const MENSAJES_POR_CODIGO: Record<string, string> = {
  IDENTIDAD_SIN_ADMINISTRADOR:
    'No se guardó: la organización se quedaría sin nadie que administre usuarios y roles. Dejá el permiso «Usuarios, roles y permisos» en algún rol que tenga usuarios activos y volvé a intentar.',
}

export function mensajeDeErrorDeRol(codigo: string | null, mensajeDelServidor: string): string {
  return (codigo !== null ? MENSAJES_POR_CODIGO[codigo] : undefined) ?? mensajeDelServidor
}
