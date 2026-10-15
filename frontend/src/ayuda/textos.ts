/**
 * Archivo único de textos de ayuda contextual (change 16b, ADR-051, `design.md` D3 y D9).
 *
 * - Cada pantalla pide su ayuda por clave (`<Ayuda clave="descuentos.medida" />` o
 *   `<Campo ayuda="descuentos.medida">`); ninguna escribe un texto por su cuenta.
 *   `ClaveDeAyuda` y `TemaDeAyuda` son tipos derivados de este archivo: una clave mal escrita
 *   no compila.
 * - `reglas` lista los IDs de `docs/01-dominio.md` o los ADR en que se apoya el texto. Sirven
 *   para mantenerlo (si cambia la regla, se busca su ID acá) y NO se muestran en pantalla
 *   (D4 = A). `tests/unit/ayuda/trazabilidad.test.ts` exige que existan.
 * - Texto plano. Un asterisco (`*x*`) marca énfasis en cursiva y dos (`**x**`) negrita; el
 *   resto se muestra tal cual. Un `ejemplo` va en un recuadro aparte.
 * - Los textos son los aprobados por el usuario el 2026-10-15 (`design.md` D9, "Revisión del
 *   usuario"); un cambio de texto se aprueba antes de editar este archivo.
 */

export interface SeccionDeTema {
  titulo: string
  parrafos: readonly string[]
  ejemplo?: string
}

export interface TemaDeAyudaDef {
  titulo: string
  reglas: readonly string[]
  secciones: readonly SeccionDeTema[]
}

export const TEMAS = {
  descuentos: {
    titulo: 'Cómo se aplican los descuentos',
    reglas: ['DSC-03', 'DSC-04', 'DSC-05', 'ADR-050'],
    secciones: [
      {
        titulo: 'En qué orden se resuelven',
        parrafos: [
          'En una venta pueden cumplirse varias reglas a la vez; el sistema las resuelve siempre en este orden.',
        ],
      },
      {
        titulo: '1. Qué reglas se cumplen',
        parrafos: [
          'Se revisa cada regla activa y vigente; para saber si se cumple se mira siempre la venta antes de cualquier descuento (cantidades y precios de lista).',
        ],
        ejemplo:
          'Ej.: con "≥ 20 cajas → 5 %", 19 cajas + 5 botellas de un vino x6 = 19,83 cajas, no se cumple; 20 cajas sí.',
      },
      {
        titulo: '2. Entre las no acumulables gana una sola',
        parrafos: [
          'Gana la que más descuento da en pesos en toda la venta; la prioridad solo desempata si dan exactamente lo mismo (gana el número más bajo).',
        ],
        ejemplo:
          'Ej.: 12 cajas de Vino A ($150.000) y 10 de Vino B ($86.000); "≥ 20 cajas → 5 %" sobre toda la venta daría $11.800 y "≥ 10 cajas de Vino A → 8 %" daría $12.000: gana la segunda y Vino B queda sin descuento aunque la otra lo incluía.',
      },
      {
        titulo: '3. Las acumulables, una después de otra',
        parrafos: [
          'Las acumulables se suman una después de otra, en orden de prioridad, cada una sobre el precio que dejó la anterior.',
        ],
        ejemplo: 'Ej.: 8 % y después 2 % = 9,84 %, no 10 %.',
      },
      {
        titulo: '4. El descuento manual, al final',
        parrafos: [
          'Al final, el descuento manual del vendedor sobre lo que quedó: uno general para toda la venta o uno distinto en un producto, que reemplaza al general en ese producto.',
        ],
      },
    ],
  },
  topes: {
    titulo: 'Cómo funcionan los topes',
    reglas: ['DSC-06', 'ADR-050'],
    secciones: [
      {
        titulo: 'Qué es el tope',
        parrafos: [
          'El tope es cuánto descuento manual puede dar alguien sin pedir permiso; se configura por rol en "Topes por rol". Solo cuenta el descuento manual (lo de las reglas automáticas no suma).',
        ],
      },
      {
        titulo: 'Cuándo se revisa',
        parrafos: [
          'Se revisa una vez por venta, contra el porcentaje manual más alto que haya quedado en algún producto.',
        ],
      },
      {
        titulo: 'Qué pasa si se supera',
        parrafos: [
          'Si lo supera, hace falta una autorización, y una sola alcanza para toda la venta: puede darla el mismo vendedor si tiene el permiso de autorizar, o un supervisor con su PIN. Quien autoriza puede aprobar cualquier porcentaje, aunque su propio tope sea menor; queda registrado quién autorizó.',
        ],
      },
      {
        titulo: 'Los topes iniciales',
        parrafos: [
          'Los roles empiezan con 0 %, salvo el Administrador (sin tope): hasta configurarlos, cualquier descuento manual pide autorización.',
        ],
        ejemplo:
          'Ej. con tope 5 %: 5 % a toda la venta pasa directo; 5 % a toda la venta y 10 % a un producto pide una autorización; 10 % a toda la venta pero 3 % puesto en cada producto → el máximo que quedó es 3 % y pasa directo.',
      },
    ],
  },
  precio: {
    titulo: 'Cómo se calcula el precio de una lista',
    reglas: ['PRC-11', 'PRC-12', 'PRC-13', 'PRC-14', 'PRC-15', 'PRC-17', 'CST-04'],
    secciones: [
      {
        titulo: 'Los tres pasos',
        parrafos: ['Cada precio sale de tres pasos y después se publica.'],
      },
      {
        titulo: '1. El costo',
        parrafos: [
          'El costo informado vigente del producto (no el promedio), llevado a su presentación de referencia, por ejemplo la caja.',
        ],
      },
      {
        titulo: '2. El margen',
        parrafos: [
          'La regla de margen más específica que le corresponda, en este orden: producto, marca, categoría, proveedor o la de toda la lista.',
        ],
      },
      {
        titulo: '3. El redondeo',
        parrafos: ['Al múltiplo de la lista, o al de su categoría si tiene uno propio.'],
        ejemplo:
          'Ej.: vino con costo $6.000 y margen bruto 30 % → $8.571,43; redondeo a múltiplo 100 hacia arriba → $8.600.',
      },
      {
        titulo: 'Nada cambia hasta que publicás',
        parrafos: [
          'Cargar un costo o cambiar una regla no toca los precios; primero generás un borrador, que recalcula todo y avisa lo que conviene revisar, y después lo publicás, ahora o con fecha. Los precios puestos a mano se mantienen de un borrador al siguiente.',
        ],
      },
    ],
  },
} as const satisfies Record<string, TemaDeAyudaDef>

export type TemaDeAyuda = keyof typeof TEMAS

export interface EntradaDeAyuda {
  titulo: string
  texto: string
  ejemplo?: string
  reglas: readonly string[]
  verMas?: TemaDeAyuda
}

export const AYUDAS = {
  // --- Descuentos: formulario de regla, detalle y topes por rol ---
  'descuentos.alcance': {
    titulo: 'Alcance de la regla',
    texto:
      '¿A qué productos se aplica la regla? *Toda la venta*: cuenta y descuenta todo lo vendido. *Productos, categorías o marcas*: solo lo que coincida con alguno de los que elijas.',
    ejemplo:
      'Ej.: si elegís la marca Bodega Norte y la categoría Cervezas, entran todos los vinos de Bodega Norte y todas las cervezas.',
    reglas: ['DSC-02', 'ADR-050'],
    verMas: 'descuentos',
  },
  'descuentos.medida': {
    titulo: 'Medida',
    texto:
      'Qué se cuenta para saber si la regla se cumple. *Cajas equivalentes*: lo vendido pasado a cajas, aunque se venda suelto (15 botellas de un vino que viene x6 = 2,5 cajas). *Unidades*: botellas o latas sueltas. *Importe*: pesos, a precio de lista, antes de descuentos.',
    reglas: ['DSC-03', 'ADR-050'],
    verMas: 'descuentos',
  },
  'descuentos.umbral': {
    titulo: 'Umbral',
    texto:
      'El número que hay que alcanzar. En cajas admite decimales (2,5); en unidades, solo enteros (60); en importe, pesos con centavos ($31.250,00).',
    reglas: ['DSC-03'],
  },
  'descuentos.accion': {
    titulo: 'Acción',
    texto:
      'Qué descuento se hace. *Porcentaje*: se descuenta ese % de cada producto que entra en la regla. *Importe fijo*: un monto total que se reparte entre esos productos según lo que vale cada uno.',
    ejemplo: 'Ej.: $1.000 entre un producto de $31.250 y otro de $4.300 → $879,04 y $120,96.',
    reglas: ['DSC-04', 'DSC-07'],
    verMas: 'descuentos',
  },
  'descuentos.prioridad': {
    titulo: 'Prioridad',
    texto:
      '1 es la más importante. Si se cumplen varias reglas no acumulables, gana la que **más descuento da**, no la de prioridad 1: la prioridad solo decide si dan exactamente lo mismo. En las acumulables, indica en qué orden se aplican.',
    reglas: ['DSC-05', 'ADR-050'],
    verMas: 'descuentos',
  },
  'descuentos.acumulable': {
    titulo: 'Acumulable',
    texto:
      '*No acumulable*: si se cumplen varias, se aplica solo una, la que más descuento da. *Acumulable*: se suma a las demás, y cada una se calcula sobre el precio que dejó la anterior.',
    ejemplo: 'Ej.: 8 % y después 2 % dan 9,84 %, no 10 %.',
    reglas: ['DSC-03', 'DSC-05', 'ADR-050'],
    verMas: 'descuentos',
  },
  'descuentos.vigencia': {
    titulo: 'Vigencia',
    texto:
      "Desde cuándo y hasta cuándo aplica. Si dejás 'desde' vacío, aplica desde que la activás. Si dejás 'hasta' vacío, no vence.",
    ejemplo: 'Ej.: desde el 1/11 hasta el 1/12 = todo noviembre.',
    reglas: ['ADR-050'],
  },
  'descuentos.activar': {
    titulo: 'Activar',
    texto:
      'Una regla solo se puede editar mientras es borrador. Activada, solo se puede pausar, reactivar o ponerle fecha de fin. Para cambiarle otra cosa, pausala y creá una nueva.',
    reglas: ['ADR-050'],
  },
  'descuentos.tope': {
    titulo: 'Tope de descuento',
    texto:
      'Cuánto descuento manual puede dar este rol sin pedir autorización. No limita los descuentos automáticos de las reglas. Si el vendedor pasa el tope en algún producto, la venta necesita **una** autorización, que vale para toda la venta. Los roles empiezan con 0 %, salvo el Administrador.',
    ejemplo:
      'Ej.: con tope 5 %, un 3 % a toda la venta pasa directo; un 10 % a un producto pide autorización.',
    reglas: ['DSC-06', 'ADR-050'],
    verMas: 'topes',
  },

  // --- Listas de precios ---
  'precios.redondeo': {
    titulo: 'Redondeo',
    texto:
      'Para que los precios queden redondos. El precio calculado se lleva al múltiplo que elijas: hacia arriba, hacia abajo o al más cercano (si queda justo en la mitad, sube). Se redondea el precio sin IVA.',
    ejemplo: 'Ej.: $8.571,43 con múltiplo 100 → $8.600 hacia arriba o al más cercano; $8.500 hacia abajo.',
    reglas: ['PRC-01', 'PRC-14', 'PRC-15'],
    verMas: 'precio',
  },
  'precios.redondeoCategoria': {
    titulo: 'Redondeo por categoría',
    texto:
      'Permite que una categoría redondee distinto que el resto de la lista. Si está activo, manda sobre el redondeo de la lista para los productos de esa categoría. Si al redondear el precio queda en $0, el producto queda sin precio.',
    reglas: ['PRC-14'],
    verMas: 'precio',
  },
  'precios.tipoMargen': {
    titulo: 'Tipo de margen',
    texto:
      'Cómo se calcula el precio a partir del costo. *Markup*: al costo se le suma un % del costo. *Margen bruto*: el % es la ganancia sobre el precio de venta (tiene que ser menor que 100 %).',
    ejemplo: 'Ej.: costo $6.000 y 30 % → markup $7.800; margen bruto $8.571,43.',
    reglas: ['PRC-12'],
    verMas: 'precio',
  },
  'precios.alcanceMargen': {
    titulo: 'Se aplica a',
    texto:
      'A qué productos aplica este margen. Si a un producto le corresponden varias reglas, manda la más específica, en este orden: producto, marca, categoría, proveedor y, por último, la de toda la lista.',
    ejemplo:
      'Ej.: si Cervezas tiene 25 % y la cerveza X tiene su propia regla de 20 %, la cerveza X va con 20 %. Los cambios se ven recién en el próximo borrador.',
    reglas: ['PRC-13'],
    verMas: 'precio',
  },
  'precios.borrador': {
    titulo: 'Borrador de precios',
    texto:
      'Los precios nuevos se preparan en un borrador antes de publicarlos. Cargar un costo nuevo no cambia ningún precio: hay que generar el borrador, que recalcula todos los productos. Los precios puestos a mano se mantienen. Hay un solo borrador por lista; regenerarlo reemplaza el anterior.',
    reglas: ['PRC-17', 'PRC-18'],
    verMas: 'precio',
  },
  'precios.senales': {
    titulo: 'Señales del precio',
    texto:
      'Avisos para revisar antes de publicar. *Costos distintos por presentación*: la botella sale distinto si se compró suelta o en caja. *Otra regla de IVA*: el costo se cargó con otra condición frente al IVA. *Margen menor*: el precio puesto a mano quedó por debajo del calculado.',
    reglas: ['PRC-11', 'PRC-17'],
  },
  'precios.sinPrecio': {
    titulo: 'Productos sin precio',
    texto:
      'Productos activos a los que el borrador no les pudo calcular precio. Pasa si les falta el costo, una regla de margen o la presentación de referencia, o si el precio da $0 o menos. Si ya corregiste lo que faltaba, regenerá el borrador. Para ponerle precio a mano, el producto tiene que tener presentación de referencia.',
    reglas: ['PRC-19'],
  },
  'precios.precioManual': {
    titulo: 'Precio manual',
    texto:
      'Para fijar un precio a mano en lugar del calculado. Se mantiene en los próximos borradores, que te avisan si quedó por debajo del calculado. Se puede poner aunque el producto no tenga costo.',
    reglas: ['PRC-16', 'PRC-17'],
  },
  'precios.publicacion': {
    titulo: 'Vigencia de la publicación',
    texto:
      "Desde cuándo rigen los precios nuevos. Si dejás 'desde' vacío, rigen apenas publicás (nunca puede ser una fecha pasada). Cuando empieza la nueva versión, la anterior deja de regir sola; si la nueva tiene 'hasta' y vence, vuelve a regir la anterior. Solo se puede anular una publicación que todavía no empezó.",
    reglas: ['PRC-02', 'PRC-03', 'PRC-05'],
    verMas: 'precio',
  },

  // --- Compras y costos ---
  'costos.valorConIva': {
    titulo: 'Valor',
    texto:
      'El precio de la presentación como figura en la factura. Si marcás que incluye IVA, el sistema se lo saca al costo, porque como responsable inscripto ese IVA lo recuperás.',
    ejemplo: 'Ej.: caja x12 a $18.000 con IVA → $18.000 / 1,21 / 12 = unos $1.239,67 por botella.',
    reglas: ['CST-02', 'CST-06'],
  },
  'costos.valorPagado': {
    titulo: 'Valor pagado',
    texto:
      'Lo que pagaste por la presentación, con el IVA incluido. Como el IVA no lo recuperás, es parte del costo y no se descuenta.',
    ejemplo: 'Ej.: caja x12 a $21.780 → $21.780 / 12 = $1.815 por botella.',
    reglas: ['CST-02', 'CST-06'],
  },
  'costos.bonificacion': {
    titulo: 'Bonificación',
    texto:
      'El descuento que te hizo el proveedor en ese producto. Se resta del valor antes de calcular el costo.',
    ejemplo: 'Ej.: caja x12 a $18.000 con 10 % → $16.200, o sea $1.350 por botella.',
    reglas: ['CST-02'],
  },
  'costos.costoBase': {
    titulo: 'Costo base',
    texto:
      'Lo que te cuesta una sola botella o lata. Es el costo que el sistema usa para todo (precios y ganancia de las ventas) y se calcula a partir de la presentación que compraste.',
    ejemplo: 'Ej.: caja x12 a $18.000 sin IVA → $1.500 por botella.',
    reglas: ['CST-02', 'CMP-02'],
  },
  'compras.totalFactura': {
    titulo: 'Total de factura',
    texto:
      'El total que figura en la factura del proveedor. El sistema te sugiere uno sumando los productos (con su IVA, si corresponde); corregilo si no coincide. Este total es lo que le debés al proveedor; el costo de la mercadería se calcula con los valores de cada producto, no con este total.',
    reglas: ['CMP-02', 'CMP-03'],
  },
  'compras.costoPromedioEInformado': {
    titulo: 'Costo promedio y costo informado',
    texto:
      'Al registrar la compra, el sistema ya actualizó el **costo promedio**, que se usa para calcular la ganancia de cada venta. El **costo informado** es otro: es el que usa la lista de precios, y solo cambia si marcás esta opción.',
    ejemplo: 'Ej.: tenías 60 botellas a $1.000 y compraste 60 a $1.100 → el promedio queda en $1.050.',
    reglas: ['CST-04', 'CST-11', 'CMP-04'],
  },

  // --- Stock y jornadas ---
  'stock.requiereToma': {
    titulo: 'Requiere toma',
    texto:
      'Para ubicaciones que un vendedor usa durante su jornada, como un vehículo. Mientras un vendedor la tiene tomada, solo su jornada puede mover el stock de ahí. Los vehículos siempre la requieren.',
    reglas: ['STK-02', 'STK-09', 'RUT-01'],
  },
  'stock.tomaActual': {
    titulo: 'Toma actual',
    texto:
      "Muestra qué jornada tiene tomada esta ubicación. Mientras la jornada está abierta, solo ese vendedor (desde su dispositivo) puede mover el stock. Cuando pasa a rendición, ya nadie puede, salvo quien tiene el permiso 'Liberar ubicación'.",
    reglas: ['STK-09', 'RUT-01'],
  },
  'stock.liberacion': {
    titulo: 'Liberar ubicación',
    texto:
      'Destraba la ubicación cuando una jornada quedó trabada (por ejemplo, se le rompió el teléfono al vendedor). No toca el stock del vehículo. Pide un motivo y queda registrado quién lo hizo. Si después llegan ventas de esa jornada desde el dispositivo, se aceptan, pero quedan marcadas para revisar.',
    reglas: ['RUT-09', 'STK-09', 'AUD-01'],
  },
} as const satisfies Record<string, EntradaDeAyuda>

export type ClaveDeAyuda = keyof typeof AYUDAS
