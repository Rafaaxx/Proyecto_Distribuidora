from datetime import UTC, datetime


def test_system_clock_devuelve_hora_actual_en_utc():
    from app.core.clock import SystemClock

    before = datetime.now(UTC)
    clock = SystemClock()
    ahora = clock.now()
    after = datetime.now(UTC)

    assert ahora.tzinfo is not None
    assert ahora.utcoffset() == UTC.utcoffset(ahora)
    assert before <= ahora <= after


def test_fixed_clock_devuelve_siempre_el_mismo_momento_fijado():
    from app.core.clock import FixedClock

    momento = datetime(2026, 1, 15, 10, 30, tzinfo=UTC)
    clock = FixedClock(momento)

    assert clock.now() == momento
    assert clock.now() == momento
