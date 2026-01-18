"""
SPRINT C2.30: Tests para schedule tick y cálculo "toca ejecutar".
"""

import pytest
from datetime import datetime, time, timedelta

from backend.shared.schedule_models import ScheduleV1
from backend.shared.schedule_tick import should_execute_now


@pytest.fixture
def daily_schedule():
    """Schedule diario para tests."""
    now = datetime.now()
    return ScheduleV1(
        schedule_id="test_daily",
        enabled=True,
        plan_id="test_plan",
        dry_run=False,
        cadence="daily",
        at_time="09:00",
        weekday=None,
        own_company_key="F63161988",
        platform_key="egestiona",
        coordinated_company_key="test_co",
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def weekly_schedule():
    """Schedule semanal para tests."""
    now = datetime.now()
    return ScheduleV1(
        schedule_id="test_weekly",
        enabled=True,
        plan_id="test_plan",
        dry_run=False,
        cadence="weekly",
        at_time="09:00",
        weekday=0,  # Lunes
        own_company_key="F63161988",
        platform_key="egestiona",
        coordinated_company_key="test_co",
        created_at=now,
        updated_at=now,
    )


def test_should_execute_now_daily_enabled(daily_schedule):
    """Test: daily schedule debe ejecutarse si la hora pasó y no se ejecutó hoy."""
    # Simular hora actual: 10:00 (después de 09:00)
    now = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    
    # Sin last_run_at: debe ejecutarse
    result = should_execute_now(daily_schedule, now)
    assert result is True


def test_should_execute_now_daily_already_run_today(daily_schedule):
    """Test: daily schedule NO debe ejecutarse si ya se ejecutó hoy."""
    now = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    
    # Ya se ejecutó hoy
    daily_schedule.last_run_at = now.replace(hour=9, minute=30)
    
    result = should_execute_now(daily_schedule, now)
    assert result is False


def test_should_execute_now_daily_before_time(daily_schedule):
    """Test: daily schedule NO debe ejecutarse si aún no es la hora."""
    # Simular hora actual: 08:00 (antes de 09:00)
    now = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
    
    result = should_execute_now(daily_schedule, now)
    assert result is False


def test_should_execute_now_daily_disabled(daily_schedule):
    """Test: daily schedule NO debe ejecutarse si está deshabilitado."""
    daily_schedule.enabled = False
    now = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    
    result = should_execute_now(daily_schedule, now)
    assert result is False


def test_should_execute_now_weekly_correct_day(weekly_schedule):
    """Test: weekly schedule debe ejecutarse si es el día correcto y la hora pasó."""
    # Simular lunes 10:00
    now = datetime.now()
    # Ajustar a lunes
    days_ahead = (0 - now.weekday()) % 7
    if days_ahead == 0 and now.hour < 9:
        days_ahead = 7
    monday = now + timedelta(days=days_ahead)
    monday = monday.replace(hour=10, minute=0, second=0, microsecond=0)
    
    result = should_execute_now(weekly_schedule, monday)
    assert result is True


def test_should_execute_now_weekly_wrong_day(weekly_schedule):
    """Test: weekly schedule NO debe ejecutarse si no es el día correcto."""
    # Simular martes (weekday=1, schedule es lunes=0)
    now = datetime.now()
    days_ahead = (1 - now.weekday()) % 7
    if days_ahead == 0 and now.weekday() != 1:
        days_ahead = 7
    tuesday = now + timedelta(days=days_ahead)
    tuesday = tuesday.replace(hour=10, minute=0, second=0, microsecond=0)
    
    result = should_execute_now(weekly_schedule, tuesday)
    assert result is False


def test_should_execute_now_weekly_already_run_this_week(weekly_schedule):
    """Test: weekly schedule NO debe ejecutarse si ya se ejecutó esta semana."""
    now = datetime.now()
    days_ahead = (0 - now.weekday()) % 7
    if days_ahead == 0 and now.hour < 9:
        days_ahead = 7
    monday = now + timedelta(days=days_ahead)
    monday = monday.replace(hour=10, minute=0, second=0, microsecond=0)
    
    # Ya se ejecutó hace 2 días (esta semana)
    weekly_schedule.last_run_at = monday - timedelta(days=2)
    
    result = should_execute_now(weekly_schedule, monday)
    assert result is False
