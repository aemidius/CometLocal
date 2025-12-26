"""
Tests para fill_by_label en BrowserController v4.6.0
"""

import pytest
import tempfile
import os
from pathlib import Path

pytestmark = pytest.mark.asyncio


class TestBrowserFillByLabel:
    """Tests para rellenado de campos por etiqueta"""
    
    async def test_fill_field_by_label_with_for_attribute(self):
        """Test que rellena un campo usando label con atributo 'for'"""
        from backend.browser.browser import BrowserController
        
        browser = BrowserController()
        await browser.start(headless=True)
        
        try:
            # Crear una página HTML de prueba
            html_content = """
            <!DOCTYPE html>
            <html>
            <body>
                <label for="issue_date">Fecha de expedición</label>
                <input type="date" id="issue_date" name="issue_date">
            </body>
            </html>
            """
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                f.write(html_content)
                temp_path = f.name
            
            try:
                file_url = f"file://{temp_path}"
                await browser.goto(file_url)
                
                success, obs = await browser.fill_field_by_label("Fecha de expedición", "2025-03-01")
                
                assert success is True
                assert obs is not None
                
                # Verificar que el valor se escribió
                value = await browser.page.evaluate("() => document.getElementById('issue_date').value")
                assert value == "2025-03-01"
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        finally:
            await browser.close()
    
    async def test_fill_field_by_label_adjacent_sibling(self):
        """Test que rellena un campo usando label adyacente sin atributo 'for'"""
        from backend.browser.browser import BrowserController
        
        browser = BrowserController()
        await browser.start(headless=True)
        
        try:
            html_content = """
            <!DOCTYPE html>
            <html>
            <body>
                <label>Fecha de caducidad</label>
                <input type="date" name="expiry_date">
            </body>
            </html>
            """
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                f.write(html_content)
                temp_path = f.name
            
            try:
                file_url = f"file://{temp_path}"
                await browser.goto(file_url)
                
                success, obs = await browser.fill_field_by_label("Fecha de caducidad", "2026-03-01")
                
                assert success is True
                assert obs is not None
                
                # Verificar que el valor se escribió
                value = await browser.page.evaluate("() => document.querySelector('input[name=\"expiry_date\"]').value")
                assert value == "2026-03-01"
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        finally:
            await browser.close()
    
    async def test_fill_by_label_candidates_success(self):
        """Test que fill_by_label_candidates encuentra el label correcto"""
        from backend.browser.browser import BrowserController
        
        browser = BrowserController()
        await browser.start(headless=True)
        
        try:
            html_content = """
            <!DOCTYPE html>
            <html>
            <body>
                <label for="worker">Trabajador</label>
                <input type="text" id="worker" name="worker_name">
            </body>
            </html>
            """
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                f.write(html_content)
                temp_path = f.name
            
            try:
                file_url = f"file://{temp_path}"
                await browser.goto(file_url)
                
                label_candidates = ["Nombre del trabajador", "Trabajador", "Nombre"]
                success, obs = await browser.fill_by_label_candidates(label_candidates, "Juan Pérez")
                
                assert success is True
                assert obs is not None
                
                # Verificar que el valor se escribió
                value = await browser.page.evaluate("() => document.getElementById('worker').value")
                assert value == "Juan Pérez"
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        finally:
            await browser.close()
    
    async def test_fill_by_label_candidates_all_fail(self):
        """Test que fill_by_label_candidates devuelve False si ningún candidato funciona"""
        from backend.browser.browser import BrowserController
        
        browser = BrowserController()
        await browser.start(headless=True)
        
        try:
            html_content = """
            <!DOCTYPE html>
            <html>
            <body>
                <p>No hay formulario aquí</p>
            </body>
            </html>
            """
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                f.write(html_content)
                temp_path = f.name
            
            try:
                file_url = f"file://{temp_path}"
                await browser.goto(file_url)
                
                label_candidates = ["Fecha de expedición", "Fecha de emisión", "Fecha"]
                success, obs = await browser.fill_by_label_candidates(label_candidates, "2025-03-01")
                
                assert success is False
                assert obs is not None
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        finally:
            await browser.close()


















