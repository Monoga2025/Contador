# Mejoras aplicadas (post-auditoría)

Resumen de los cambios realizados tras la auditoría del proyecto LuxFinance / Asesor Financiero IA.

---

## Lista de cambios realizados

### 🔴 CRÍTICO

1. **Unificar UI en index (eliminar doble layout)**  
   - Eliminado el bloque `.shell` completo (sidebar legacy, main-area con dashboard duplicado, quick-form, mission-control, cfo-plan duplicado, FABs legacy).  
   - Conservada solo la UI lux: lux-sidebar, lux-main, lux-hero, lux-cfo-wrap, sección #cfo-plan única, movimientos, filtros, botón "Ver esperados".  
   - Modales y drawers (modal-editar-movimiento, drawer-esperados, ia-drawer) movidos fuera de .shell y referenciados por el mismo JS.  
   - addItemsToTable en app.js ahora envía los gastos de voz/IA por POST a /add-transaction en lugar de rellenar un formulario inexistente.  
   - Notificaciones actualizan también notif-badge-lux.

2. **Seed vacío**  
   - `seed_fixed_items()` deja de inyectar datos de una persona concreta; `base_items` queda como lista vacía. El usuario configura ingresos y gastos en /config.

3. **Degradación sin GEMINI_API_KEY**  
   - `get_gemini_model()` devuelve `None` si no hay API key en lugar de lanzar RuntimeError.  
   - Todos los endpoints que usan IA comprueban `if not model` y devuelven mensajes claros (ej. "Configura GEMINI_API_KEY en .env") o 503 con detalle, sin romper la app.

4. **Mensajes Analytics y remap_category**  
   - analytics.js: mensajes más claros cuando no hay datos ("Genera un cierre de mes (snapshot) desde Inicio o Config", "Añade movimientos en Inicio para ver la proyección").  
   - remap_category: docstring y texto del modal alineados con "categoría analítica" (se reasigna por `Transaction.category`, no por concepto).  
   - Modal "Reasignar categorías del gráfico" con helper explicando reasignación de categorías analíticas.

---

### 🟡 IMPORTANTE

5. **Helper único para movimientos reales**  
   - Añadidas `_es_movimiento_fijo(tx)` y `_es_movimiento_real(tx)` y sustituidas todas las list comprehensions repetidas que filtraban por "fijo mensual".

6. **Paginación implícita en "Todos los movimientos"**  
   - Solo se muestran los últimos 60 días en la vista por días (cutoff = today - 60 días). Los totales (ingresos, gastos, disponible) siguen usando todos los movimientos reales del mes.

7. **datetime.utcnow → datetime.now(timezone.utc)**  
   - MonthSnapshot.created_at, Notification.created_at, UserProfile.updated_at usan `datetime.now(timezone.utc)` o `default_factory=lambda: datetime.now(timezone.utc)`.

8. **Migraciones con log**  
   - `migrate_add_missing_columns()` registra en log (warning) los errores que no sean "duplicate column" / "already exists", para no silenciar fallos de permisos o esquema.

---

### 🔵 DISEÑO

9. **Textos en español en perfil**  
   - "Personality Data" → "Datos de perfil", "ID Card" → "Resumen" en templates/perfil.html.

10. **Colores de gráficos desde design system**  
    - app.js (initCharts): borderColor de ingresos/gastos leídos de getComputedStyle(--lux-success, --lux-danger); backgroundColor se mantiene en rgba fijo por compatibilidad.

---

### ⚡ IA

11. **Pareja/planes desde perfil**  
    - El bloque "Metas y planes con su novia" en get_advice solo se inyecta si en UserProfile.contexto_personal aparece "pareja" o "novia". Si no, el prompt no incluye esa sección.

12. **Clasificador con few-shot**  
    - _pick_category_from_list: prompt con ejemplos (Arriendo→Vivienda, Supermercado→Alimentación, etc.) e instrucción explícita de responder solo una categoría de la lista.

13. **Parseo JSON robusto en parse-expenses**  
    - En parse_expenses_from_text y parse_expenses_from_image: si json.loads(raw) falla, se intenta extraer un array con regex `\[[\s\S]*\]` y parsear eso. Mensajes de error unificados: "No se pudieron extraer ítems del texto..." / "No se pudieron leer ítems de la factura...".

---

### 🏗️ ARQUITECTURA

14. **Import único de finance_engine**  
    - `import finance_engine as fe` al inicio de main.py; eliminados los imports inline dentro de funciones.

15. **Lifespan en lugar de on_event("startup")**  
    - Sustituido @app.on_event("startup") por un context manager lifespan que ejecuta create_db_and_tables(), migrate_add_missing_columns(), seed_fixed_items y seed_month_base_data al arranque. FastAPI recibe lifespan=lifespan.

16. **SavingsBalance documentado como singleton**  
    - Docstrings en el modelo y en _get_savings_balance aclarando que se usa un solo registro (el primero).

---

### 📱 MOBILE

17. **Tablas con overflow horizontal**  
    - En design-system.css: .table-wrapper { overflow-x: auto; -webkit-overflow-scrolling: touch; } para que tablas no rompan el layout en pantallas pequeñas.

18. **Touch targets en acciones de movimientos**  
    - .mov-actions .btn-link con min-height: 44px, min-width: 44px, padding y flex para que Editar/Borrar cumplan tamaño mínimo táctil.

19. **Sheet agregar**  
    - La .lux-sheet ya tenía max-height: 92vh, overflow-y: auto y padding-bottom con env(safe-area-inset-bottom); no se modificó.

---

## Archivos modificados

| Archivo | Cambios |
|---------|--------|
| `main.py` | Seed vacío, get_gemini_model devuelve None, comprobaciones en todos los usos de IA, helper _es_movimiento_fijo/real, paginación 60 días, datetime timezone, migraciones con log, remap_category docstring, prompts pareja condicional, clasificador few-shot, parseo JSON con regex, lifespan, import fe al inicio, docstrings SavingsBalance |
| `templates/index.html` | Sección #cfo-plan en lux, botón "Ver esperados", modal/drawer/ia-drawer fuera de .shell, eliminado bloque .shell completo |
| `templates/perfil.html` | Textos "Datos de perfil" y "Resumen" en español |
| `templates/index.html` (modal etiquetas) | Título y helper de reasignar categorías |
| `static/app.js` | addItemsToTable POST a /add-transaction, notif-badge-lux en notificaciones, colores de gráficos desde CSS variables |
| `static/analytics.js` | Mensajes claros cuando no hay datos mensuales o proyección |
| `static/css/design-system.css` | .table-wrapper overflow-x |
| `static/css/pages/home.css` | .mov-actions .btn-link touch targets 44px |

---

## Score estimado por categoría (después del fix)

| Categoría    | Antes | Después (estimado) |
|-------------|-------|---------------------|
| Crítico     | 3     | **7**               |
| Importante  | 4     | **6**               |
| Diseño      | 4     | **6**               |
| IA          | 5     | **7**               |
| Arquitectura| 4     | **6**               |
| Mobile      | 4     | **6**               |
| **Global**  | **4** | **~6.5**            |

---

## Pendiente (no resuelto en esta pasada)

- **Streaming** en el chat del asesor (respuesta progresiva): no implementado; sigue siendo carga completa.  
- **Paginación explícita** "Cargar más" en movimientos: solo se aplicó límite de 60 días; no hay botón "Ver más".  
- **Refactor de main.py** en módulos (models, routes, services, prompts): no realizado; el archivo sigue siendo único.  
- **Diferenciación de errores de IA** en JSON (ej. `error_type: "no_api_key"`) para el front: solo mensajes claros; no clave estructurada.  
- **Constraint único o política explícita** en BD para SavingsBalance (un solo registro): solo documentado; no migración.  
- **Gasto con subgastos (detalle de factura)** en la UI lux: el flujo sigue en el panel legacy que se eliminó; para usarlo habría que reañadir un sheet o enlace "Gasto con detalle" en el flujo actual.
