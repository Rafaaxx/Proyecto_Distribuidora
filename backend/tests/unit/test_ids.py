from uuid import UUID


def test_nuevo_id_es_uuid_version_7():
    from app.core.ids import nuevo_id

    id_generado = nuevo_id()

    assert isinstance(id_generado, UUID)
    assert id_generado.version == 7


def test_dos_ids_consecutivos_son_crecientes():
    from app.core.ids import nuevo_id

    primero = nuevo_id()
    segundo = nuevo_id()

    assert primero.version == 7
    assert segundo.version == 7
    assert primero.bytes < segundo.bytes


def test_muchos_ids_generados_son_unicos():
    from app.core.ids import nuevo_id

    ids = [nuevo_id() for _ in range(1000)]

    assert len(set(ids)) == 1000
