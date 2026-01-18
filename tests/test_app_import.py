"""
Test mínimo para verificar que backend.app se importa sin errores.
"""

def test_app_import():
    """Test: Importar backend.app no debe lanzar excepción."""
    import backend.app
    assert backend.app is not None
    assert hasattr(backend.app, 'app')
    assert backend.app.app is not None
