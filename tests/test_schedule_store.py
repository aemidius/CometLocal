"""
SPRINT C2.30: Tests para persistencia de schedules.
"""

import pytest
from datetime import datetime

from backend.shared.schedule_models import ScheduleV1, ScheduleStore
from backend.config import DATA_DIR


@pytest.fixture
def test_tenant_id():
    """Tenant ID para tests."""
    return "test_tenant_schedules"


@pytest.fixture
def store(test_tenant_id, tmp_path):
    """ScheduleStore para tests."""
    return ScheduleStore(tmp_path, test_tenant_id)


def test_save_and_load_schedule(store):
    """Test: guardar y cargar schedule."""
    now = datetime.now()
    schedule = ScheduleV1(
        schedule_id="test_schedule_1",
        enabled=True,
        plan_id="plan_123",
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
    
    store.save_schedule(schedule)
    
    schedules = store.list_schedules()
    assert len(schedules) == 1
    assert schedules[0].schedule_id == "test_schedule_1"
    assert schedules[0].plan_id == "plan_123"


def test_update_schedule(store):
    """Test: actualizar schedule existente."""
    now = datetime.now()
    schedule1 = ScheduleV1(
        schedule_id="test_schedule_1",
        enabled=True,
        plan_id="plan_123",
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
    
    store.save_schedule(schedule1)
    
    # Actualizar
    schedule1.enabled = False
    schedule1.at_time = "10:00"
    schedule1.updated_at = datetime.now()
    store.save_schedule(schedule1)
    
    schedules = store.list_schedules()
    assert len(schedules) == 1
    assert schedules[0].enabled is False
    assert schedules[0].at_time == "10:00"


def test_delete_schedule(store):
    """Test: eliminar schedule."""
    now = datetime.now()
    schedule1 = ScheduleV1(
        schedule_id="test_schedule_1",
        enabled=True,
        plan_id="plan_123",
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
    
    schedule2 = ScheduleV1(
        schedule_id="test_schedule_2",
        enabled=True,
        plan_id="plan_456",
        dry_run=False,
        cadence="weekly",
        at_time="09:00",
        weekday=0,
        own_company_key="F63161988",
        platform_key="egestiona",
        coordinated_company_key="test_co",
        created_at=now,
        updated_at=now,
    )
    
    store.save_schedule(schedule1)
    store.save_schedule(schedule2)
    
    assert len(store.list_schedules()) == 2
    
    deleted = store.delete_schedule("test_schedule_1")
    assert deleted is True
    
    schedules = store.list_schedules()
    assert len(schedules) == 1
    assert schedules[0].schedule_id == "test_schedule_2"


def test_delete_nonexistent_schedule(store):
    """Test: eliminar schedule que no existe."""
    deleted = store.delete_schedule("nonexistent")
    assert deleted is False
