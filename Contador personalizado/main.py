import json
import os
from datetime import date, datetime
from calendar import monthrange
from typing import Optional, List, Any

from fastapi import FastAPI, Depends, HTTPException, Request, Form, File, UploadFile, Body
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import SQLModel, Field, Session, create_engine, select
from dotenv import load_dotenv
import google.generativeai as genai


load_dotenv()

DATABASE_URL = "sqlite:///./finanzas.db"
engine = create_engine(DATABASE_URL, echo=False)

# Categorías analíticas fijas (para gráficas y reportes). La IA solo elige entre estas.
CATEGORIAS_ANALITICAS = [
    "Vivienda",
    "Transporte",
    "Gastos moto",
    "Alimentación",
    "Servicios",
    "Educación",
    "Salud",
    "Ocio y pareja",
    "Lujos",
    "Otros",
]


class Transaction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    date: date
    amount: float
    type: str  # "ingreso" o "gasto"
    category: str  # categoría analítica (una de CATEGORIAS_ANALITICAS)
    concept: Optional[str] = None  # concepto/descripción para mostrar (ej. Arriendo, Aseo)
    description: Optional[str] = None


class TransactionLineItem(SQLModel, table=True):
    """Subgasto / ítem de factura dentro de un gasto compuesto."""
    id: Optional[int] = Field(default=None, primary_key=True)
    transaction_id: int = Field(foreign_key="transaction.id")
    concept: str  # ej. peluche, moñas
    amount: float


class FixedItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    type: str  # "ingreso" o "gasto"
    category: str  # concepto (ej. Aseo, Arriendo)
    analytic_category: Optional[str] = None  # categoría analítica para gráficas (Vivienda, etc.)
    amount: float
    day: int  # día del mes en que normalmente se paga/cobra


class SavingsBalance(SQLModel, table=True):
    """Un solo registro: ahorro actual del usuario (cuánto tiene guardado)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    balance: float = 0.0


class Goal(SQLModel, table=True):
    """Objetivo financiero: meta de ahorro con frecuencia (una vez, semanal, mensual, anual)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    target_amount: float
    frequency: str  # "una_vez", "semanal", "mensual", "anual"
    deadline: Optional[date] = None  # opcional, para una_vez o plazo
    current_saved: float = 0.0
    notes: Optional[str] = None


class MonthSnapshot(SQLModel, table=True):
    """Snapshot del cierre de cada mes para comparar y promedios históricos."""
    id: Optional[int] = Field(default=None, primary_key=True)
    year: int = 0
    month: int = 0
    ingresos: float = 0.0
    gastos: float = 0.0
    disponible: float = 0.0
    tasa_ahorro: float = 0.0
    score_financiero: int = 0
    categoria_top_gasto: str = ""
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)


class Notification(SQLModel, table=True):
    """Notificaciones in-app para el usuario."""
    id: Optional[int] = Field(default=None, primary_key=True)
    message: str = ""
    type: str = "info"  # info, alert, success
    read: bool = False
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)


class AppSetting(SQLModel, table=True):
    """Configuración de la app (tema, etc.). key único."""
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(unique=True)
    value: str = ""


class UserProfile(SQLModel, table=True):
    """Perfil personal del usuario para que la IA actúe como CFO con contexto humano."""
    id: Optional[int] = Field(default=None, primary_key=True)
    nombre: str = ""
    edad: Optional[int] = None
    ciudad: str = ""
    ocupacion: str = ""
    situacion_actual: str = ""
    fuentes_ingreso: str = ""
    habilidades: str = ""
    restricciones: str = ""
    vision: str = ""
    tolerancia_riesgo: str = "moderado"  # conservador, moderado, agresivo
    contexto_personal: str = ""
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_theme(session: Session) -> str:
    """Devuelve 'light' o 'dark'. Por defecto 'dark'."""
    row = session.exec(select(AppSetting).where(AppSetting.key == "theme")).first()
    if not row or not row.value:
        return "dark"
    return row.value if row.value in ("light", "dark") else "dark"


def set_theme(session: Session, theme: str) -> None:
    theme = "light" if theme == "light" else "dark"
    row = session.exec(select(AppSetting).where(AppSetting.key == "theme")).first()
    if row:
        row.value = theme
        session.add(row)
    else:
        session.add(AppSetting(key="theme", value=theme))
    session.commit()


def migrate_add_missing_columns() -> None:
    """Añade columnas nuevas a tablas existentes (migración manual)."""
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE fixeditem ADD COLUMN analytic_category TEXT"))
            conn.commit()
    except Exception:
        pass  # la columna ya existe
    try:
        with engine.connect() as conn:
            conn.execute(text('ALTER TABLE "transaction" ADD COLUMN concept TEXT'))
            conn.commit()
    except Exception:
        pass
    # La tabla transactionlineitem se crea con create_all; si usas DB antigua, crear manualmente:
    # CREATE TABLE IF NOT EXISTS transactionlineitem (id INTEGER PRIMARY KEY, transaction_id INTEGER NOT NULL, concept VARCHAR NOT NULL, amount REAL NOT NULL);
    # MonthSnapshot se crea con create_all (tabla nueva)


def seed_fixed_items(session: Session) -> None:
    existing = session.exec(select(FixedItem)).first()
    if existing:
        return

    base_items = [
        # Ingresos (concept, analytic_category)
        {"type": "ingreso", "category": "Pago Maral", "analytic": "Otros", "amount": 2_000_000, "day": 1},
        {"type": "ingreso", "category": "Pago IA", "analytic": "Otros", "amount": 274_000, "day": 15},
        {"type": "ingreso", "category": "Trabajo", "analytic": "Otros", "amount": 730_000, "day": 15},
        # Gastos
        {"type": "gasto", "category": "Aseo", "analytic": "Vivienda", "amount": 35_000, "day": 1},
        {"type": "gasto", "category": "Cuota Moto", "analytic": "Transporte", "amount": 410_000, "day": 1},
        {"type": "gasto", "category": "Plan Movistar", "analytic": "Servicios", "amount": 23_000, "day": 2},
        {"type": "gasto", "category": "Parqueadero U", "analytic": "Transporte", "amount": 50_000, "day": 1},
        {"type": "gasto", "category": "GPS moto", "analytic": "Transporte", "amount": 0, "day": 5},
        {"type": "gasto", "category": "Mantenimiento", "analytic": "Transporte", "amount": 60_000, "day": 15},
        {"type": "gasto", "category": "Arriendo", "analytic": "Vivienda", "amount": 590_000, "day": 16},
        {"type": "gasto", "category": "Gasolina", "analytic": "Transporte", "amount": 80_000, "day": 10},
        {"type": "gasto", "category": "Universidad", "analytic": "Educación", "amount": 60_000, "day": 10},
        {"type": "gasto", "category": "Almuerzo", "analytic": "Alimentación", "amount": 480_000, "day": 1},
        {"type": "gasto", "category": "Comida", "analytic": "Alimentación", "amount": 120_000, "day": 1},
        {"type": "gasto", "category": "Desayuno", "analytic": "Alimentación", "amount": 120_000, "day": 1},
    ]

    for item in base_items:
        session.add(
            FixedItem(
                type=item["type"],
                category=item["category"],
                analytic_category=item.get("analytic", "Otros"),
                amount=item["amount"],
                day=item["day"],
            )
        )

    session.commit()


def seed_month_base_data(session: Session) -> None:
    today = date.today()
    year, month = today.year, today.month
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])

    fixed_items = session.exec(select(FixedItem)).all()

    for item in fixed_items:
        analytic = getattr(item, "analytic_category", None) or "Otros"
        stmt = (
            select(Transaction)
            .where(Transaction.type == item.type)
            .where(Transaction.date >= first_day)
            .where(Transaction.date <= last_day)
            .where(
                (Transaction.concept == item.category)
                | (Transaction.category == item.category)
            )
        )
        exists = session.exec(stmt).first()
        if exists:
            continue

        d = min(item.day, last_day.day)
        tx_date = date(year, month, d)
        tx = Transaction(
            date=tx_date,
            amount=item.amount,
            type=item.type,
            category=analytic,
            concept=item.category,
            description=(
                "Ingreso fijo mensual" if item.type == "ingreso" else "Gasto fijo mensual"
            ),
        )
        session.add(tx)

    session.commit()


def refresh_current_month_from_fixed(session: Session) -> None:
    """Recrea los movimientos fijos del mes actual según la tabla FixedItem."""
    today = date.today()
    year, month = today.year, today.month
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])

    # Borrar movimientos fijos de este mes (controlados por FixedItem).
    stmt_month = (
        select(Transaction)
        .where(Transaction.date >= first_day)
        .where(Transaction.date <= last_day)
    )
    month_txs = session.exec(stmt_month).all()

    fixed_items = session.exec(select(FixedItem)).all()

    for tx in month_txs:
        managed_by_fixed = any(
            (fi.type == tx.type and (fi.category == getattr(tx, "concept", None) or fi.category == tx.category))
            for fi in fixed_items
        )
        if managed_by_fixed or (tx.description and "fijo mensual" in (tx.description or "")):
            session.delete(tx)
    session.commit()

    # Volver a generarlos desde FixedItem
    seed_month_base_data(session)


def _get_savings_balance(session: Session) -> float:
    row = session.exec(select(SavingsBalance).limit(1)).first()
    return float(row.balance) if row else 0.0


def _pick_category_from_list(description: str, amount: float) -> str:
    """IA elige UNA categoría de CATEGORIAS_ANALITICAS. No crea nuevas."""
    model = get_gemini_model()
    list_str = ", ".join(f'"{c}"' for c in CATEGORIAS_ANALITICAS)
    prompt = f"""Clasificador. Descripción del gasto/ingreso: "{description}". Monto: {amount} COP.
Debes responder SOLO una de estas categorías, sin explicación: {list_str}.
Responde exactamente una palabra o frase de la lista."""
    r = model.generate_content(prompt)
    raw = (r.text or "").strip().splitlines()[0].strip() if hasattr(r, "text") else ""
    for c in CATEGORIAS_ANALITICAS:
        if c.lower() in raw.lower() or raw.lower() in c.lower():
            return c
    return "Otros"


def get_session():
    with Session(engine) as session:
        yield session


def get_gemini_model():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "No se encontró la variable de entorno GEMINI_API_KEY. "
            "Crea un archivo .env con GEMINI_API_KEY=TU_CLAVE"
        )
    genai.configure(api_key=api_key)
    # Modelo recomendado y disponible en la librería actual
    return genai.GenerativeModel("gemini-2.5-flash")


app = FastAPI(title="Asesor Financiero IA")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
def on_startup():
    create_db_and_tables()
    migrate_add_missing_columns()
    with Session(engine) as session:
        seed_fixed_items(session)
        seed_month_base_data(session)


@app.get("/", response_class=HTMLResponse)
def read_root(request: Request, session: Session = Depends(get_session)):
    stmt = select(Transaction).order_by(Transaction.date.asc(), Transaction.id.asc())
    all_transactions = session.exec(stmt).all()

    ingresos = sum(t.amount for t in all_transactions if t.type == "ingreso")
    gastos = sum(t.amount for t in all_transactions if t.type == "gasto")
    disponible = ingresos - gastos

    # Separar movimientos esperados (fijos del mes) y movimientos reales
    from datetime import date as _date

    today = _date.today()
    transactions_expected = [
        t
        for t in all_transactions
        if t.description and "fijo mensual" in t.description and t.date <= today
    ]
    transactions_real = [
        t
        for t in all_transactions
        if not (t.description and "fijo mensual" in t.description)
    ]

    real_ingresos = sum(t.amount for t in transactions_real if t.type == "ingreso")
    real_gastos = sum(t.amount for t in transactions_real if t.type == "gasto")
    real_disponible = real_ingresos - real_gastos

    ahorro_meta = ingresos * 0.2 if ingresos > 0 else 0
    ahorro_real = max(disponible, 0)
    ahorro_gap = ahorro_meta - ahorro_real
    ahorro_rate = (ahorro_real / ingresos * 100) if ingresos > 0 else 0

    pareja_keywords = [
        "novia",
        "salida",
        "cine",
        "piscina",
        "pijama",
        "starbucks",
        "bailar",
        "solecita",
        "plan pareja",
    ]
    gasto_pareja = 0
    for t in all_transactions:
        if t.type != "gasto":
            continue
        cat = (t.category or "").lower()
        if any(k in cat for k in pareja_keywords):
            gasto_pareja += t.amount
    gasto_pareja_pct = (gasto_pareja / ingresos * 100) if ingresos > 0 else 0

    # Ahorro actual (si existe) para que la IA sepa si está gastando ahorros
    savings_balance = _get_savings_balance(session)

    # Subgastos por transacción (gastos compuestos)
    all_line_items = session.exec(select(TransactionLineItem)).all()
    line_items_by_tx = {}
    for li in all_line_items:
        line_items_by_tx.setdefault(li.transaction_id, []).append(li)

    config_saved = request.query_params.get("config_saved") == "1"
    fixed_items = list(session.exec(select(FixedItem)).all())
    first_time = len(fixed_items) == 0
    profile = session.exec(select(UserProfile).limit(1)).first()
    profile_name = (profile.nombre or "").strip() if profile else ""

    # Score financiero para la Card Hero
    import finance_engine as fe
    _dias_mes = monthrange(today.year, today.month)[1]
    _gasto_promedio = real_gastos / today.day if today.day else 0
    _runway = fe.calcular_runway(real_disponible, _gasto_promedio)
    _tasa = fe.tasa_ahorro_real(real_ingresos, real_gastos)
    _goals = list(session.exec(select(Goal)).all())
    score_financiero = fe.calcular_score_financiero(_tasa, 0, _runway, 0, len(_goals))

    # Agrupar movimientos reales por día (más reciente primero) para vista compacta
    from collections import defaultdict
    por_dia = defaultdict(list)
    for t in transactions_real:
        por_dia[t.date].append(t)
    sorted_dates = sorted(por_dia.keys(), reverse=True)
    movimientos_por_dia = []
    for d in sorted_dates:
        movimientos_por_dia.append({
            "date": d,
            "date_iso": d.isoformat(),
            "date_label": d.strftime("%a %d %b"),
            "transactions": por_dia[d],
        })

    # Primeras 7 transacciones para "Movimientos recientes" (más recientes primero)
    movimientos_recientes_7 = []
    for g in movimientos_por_dia:
        for t in g["transactions"]:
            movimientos_recientes_7.append(t)
            if len(movimientos_recientes_7) >= 7:
                break
        if len(movimientos_recientes_7) >= 7:
            break

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "first_time": first_time,
            "categorias_analiticas": CATEGORIAS_ANALITICAS,
            "transactions_expected": transactions_expected,
            "transactions_real": transactions_real,
            "movimientos_por_dia": movimientos_por_dia,
            "movimientos_recientes_7": movimientos_recientes_7,
            "line_items_by_tx": line_items_by_tx,
            "ingresos": ingresos,
            "gastos": gastos,
            "disponible": disponible,
            "config_saved": config_saved,
            "ahorro_meta": ahorro_meta,
            "ahorro_real": ahorro_real,
            "ahorro_gap": ahorro_gap,
            "ahorro_rate": ahorro_rate,
            "gasto_pareja": gasto_pareja,
            "gasto_pareja_pct": gasto_pareja_pct,
            "savings_balance": savings_balance,
            "real_ingresos": real_ingresos,
            "real_gastos": real_gastos,
            "real_disponible": real_disponible,
            "today": today.isoformat(),
            "theme": get_theme(session),
            "profile_name": profile_name,
            "score_financiero": score_financiero,
        },
    )


@app.get("/config", response_class=HTMLResponse)
def config_view(
    request: Request,
    session: Session = Depends(get_session),
    saved: bool = False,
):
    items = session.exec(select(FixedItem).order_by(FixedItem.day)).all()
    def _item_dict(i):
        return {
            "id": i.id,
            "category": i.category,
            "amount": i.amount,
            "day": i.day,
            "analytic_category": getattr(i, "analytic_category", None) or "Otros",
        }
    ingresos = [_item_dict(i) for i in items if i.type == "ingreso"]
    gastos = [_item_dict(i) for i in items if i.type == "gasto"]

    return templates.TemplateResponse(
        "config.html",
        {
            "request": request,
            "ingresos": ingresos,
            "gastos": gastos,
            "saved": saved,
            "categorias_analiticas": CATEGORIAS_ANALITICAS,
            "theme": get_theme(session),
        },
    )


@app.post("/config/save", response_class=HTMLResponse)
async def config_save(request: Request, session: Session = Depends(get_session)):
    form = await request.form()

    ingreso_ids = list(form.getlist("ingreso_id"))
    ingreso_cats = list(form.getlist("ingreso_category"))
    ingreso_analytics = list(form.getlist("ingreso_analytic"))
    ingreso_amounts = list(form.getlist("ingreso_amount"))
    ingreso_days = list(form.getlist("ingreso_day"))
    ingreso_deletes = list(form.getlist("ingreso_delete"))

    gasto_ids = list(form.getlist("gasto_id"))
    gasto_cats = list(form.getlist("gasto_category"))
    gasto_analytics = list(form.getlist("gasto_analytic"))
    gasto_amounts = list(form.getlist("gasto_amount"))
    gasto_days = list(form.getlist("gasto_day"))
    gasto_deletes = list(form.getlist("gasto_delete"))

    def process_rows(
        ids, cats, analytics, amounts, days, deletes, tipo: str
    ):
        for idx, (fid, cat, amt, d) in enumerate(zip(ids, cats, amounts, days)):
            analytic = (analytics[idx] if idx < len(analytics) else "").strip() or "Otros"
            if analytic not in CATEGORIAS_ANALITICAS:
                analytic = "Otros"
            delete_flag = False
            if tipo == "ingreso" and idx < len(ingreso_deletes):
                delete_flag = ingreso_deletes[idx] == "1"
            if tipo == "gasto" and idx < len(gasto_deletes):
                delete_flag = gasto_deletes[idx] == "1"

            cat = (cat or "").strip()
            amt = (amt or "").strip()
            d = (d or "").strip()

            if not fid and not cat and not amt:
                continue

            if fid:
                item = session.get(FixedItem, int(fid))
                if not item:
                    continue
                if delete_flag or not cat:
                    session.delete(item)
                else:
                    item.category = cat
                    item.amount = float(amt or 0)
                    item.day = max(1, min(31, int(d or 1)))
                    setattr(item, "analytic_category", analytic)
            else:
                if not cat or not amt:
                    continue
                session.add(
                    FixedItem(
                        type=tipo,
                        category=cat,
                        analytic_category=analytic,
                        amount=float(amt),
                        day=max(1, min(31, int(d or 1))),
                    )
                )

    process_rows(ingreso_ids, ingreso_cats, ingreso_analytics, ingreso_amounts, ingreso_days, ingreso_deletes, "ingreso")
    process_rows(gasto_ids, gasto_cats, gasto_analytics, gasto_amounts, gasto_days, gasto_deletes, "gasto")
    session.commit()
    refresh_current_month_from_fixed(session)
    return RedirectResponse(url="/config?saved=1", status_code=303)


@app.get("/api/config/suggest-categories")
def suggest_fixed_categories(session: Session = Depends(get_session)):
    """Sugiere categoría analítica para cada ingreso/gasto fijo usando la IA (concepto + monto)."""
    items = session.exec(select(FixedItem).order_by(FixedItem.day)).all()
    suggestions = []
    for item in items:
        try:
            suggested = _pick_category_from_list(item.category or "", float(item.amount or 0))
        except Exception:
            suggested = "Otros"
        suggestions.append({
            "id": item.id,
            "type": item.type,
            "suggested": suggested,
        })
    return {"suggestions": suggestions}


@app.get("/api/suggestions/concepts")
def get_suggestions_concepts(
    limit: int = 5,
    min_count: int = 3,
    session: Session = Depends(get_session),
):
    """Conceptos más usados (3+ veces) para sugerencias rápidas en el registro."""
    from datetime import date as _date
    from collections import Counter
    today = _date.today()
    stmt = select(Transaction).where(
        Transaction.date >= _date(today.year, today.month, 1) if today.month else today,
    )
    txs = session.exec(stmt).all()
    real = [t for t in txs if not (t.description and "fijo mensual" in (t.description or ""))]
    concepts = [t.concept or t.category or "" for t in real if (t.concept or t.category)]
    counted = Counter(c for c in concepts if c.strip())
    top = [c for c, n in counted.most_common(limit * 2) if n >= min_count][:limit]
    return {"concepts": top}


@app.post("/add-transaction", response_class=HTMLResponse)
def add_transaction(
    request: Request,
    date_str: List[str] = Form(...),
    amount: List[float] = Form(...),
    type: List[str] = Form(...),
    category: List[str] = Form(...),
    description: List[str] = Form(None),
    session: Session = Depends(get_session),
):
    from datetime import date as _date

    created_any = False
    try:
        rows = list(zip(date_str, amount, type, category, description or []))
        for d_str, amt, t, cat, desc in rows:
            desc_str = (desc or "").strip()
            if not desc_str and (amt is None or amt == 0):
                continue
            concept = desc_str or None
            # La IA asigna siempre la categoría al guardar (no manual)
            if desc_str:
                try:
                    cat = _pick_category_from_list(desc_str, float(amt or 0))
                except Exception:
                    cat = "Otros"
            else:
                cat = "Otros"

            tx_date = _date.fromisoformat(d_str) if (d_str and d_str.strip()) else _date.today()
            tx = Transaction(
                date=tx_date,
                amount=float(amt),
                type=t,
                category=cat,
                concept=concept,
                description=(desc or None),
            )
            session.add(tx)
            created_any = True
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error en datos: {exc}")

    if created_any:
        session.commit()

    return read_root(request, session)


@app.post("/add-expense-with-detail")
async def add_expense_with_detail(
    request: Request,
    session: Session = Depends(get_session),
):
    """Crea un gasto compuesto con subgastos (detalle de factura)."""
    from datetime import date as _date

    body = await request.json()
    concept = (body.get("concept") or "").strip()
    date_str = (body.get("date") or "").strip()
    category = (body.get("category") or "Otros").strip()
    if category not in CATEGORIAS_ANALITICAS:
        category = "Otros"
    line_items = body.get("line_items") or []

    if not concept:
        raise HTTPException(status_code=400, detail="Falta el concepto del gasto")
    if not date_str:
        raise HTTPException(status_code=400, detail="Falta la fecha")

    try:
        tx_date = _date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha inválida")

    total = 0.0
    valid_items = []
    for it in line_items:
        c = (it.get("concept") or "").strip()
        a = float(it.get("amount") or 0)
        if c:
            valid_items.append((c, a))
            total += a

    if not valid_items:
        raise HTTPException(status_code=400, detail="Añade al menos un subgasto (concepto y monto)")

    tx = Transaction(
        date=tx_date,
        amount=total,
        type="gasto",
        category=category,
        concept=concept,
        description="Gasto con detalle",
    )
    session.add(tx)
    session.flush()  # para tener tx.id

    for c, a in valid_items:
        session.add(TransactionLineItem(transaction_id=tx.id, concept=c, amount=a))
    session.commit()
    return {"ok": True, "transaction_id": tx.id}


@app.get("/api/transactions/{tx_id}/line-items")
def get_transaction_line_items(tx_id: int, session: Session = Depends(get_session)):
    """Devuelve los subgastos de una transacción."""
    items = session.exec(
        select(TransactionLineItem).where(TransactionLineItem.transaction_id == tx_id)
    ).all()
    return {"items": [{"id": i.id, "concept": i.concept, "amount": i.amount} for i in items]}


@app.post("/api/advice")
async def get_advice(request: Request, session: Session = Depends(get_session)):
    """Consejo de la IA con contexto enriquecido. Acepta Form (question) o JSON (question, history)."""
    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            body = await request.json()
            question = (body.get("question") or body.get("message") or "").strip()
            history = body.get("history") or []
        else:
            form = await request.form()
            question = (form.get("question") or "").strip()
            history = []
            hist_raw = form.get("history")
            if hist_raw:
                try:
                    history = json.loads(hist_raw) if isinstance(hist_raw, str) else hist_raw
                except Exception:
                    pass
        if not question:
            raise HTTPException(status_code=400, detail="Falta question o message")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Cuerpo inválido")

    ctx = _build_advice_context(session)
    master = build_master_context(session)
    planes_pareja = [
        "Acercarnos más a Dios", "Hacer un deporte juntos", "Conocer un pueblo cada 20 días",
        "Ir a piscina", "Acciones para mejorar en pareja", "Comprar abono para Ofuca (fin de semana)",
        "Hacer una actividad juntos (cultural) cada dos días", "Skincare juntos (spa mensual)",
        "Match + cita planeada", "Hacer receta de IG deliciosa", "Pijama juntos",
        "Almuerzo diferente domingos (planear con anticipación)", "Plan natural", "Ir por un Starbucks",
        "Ir a bailar y algo de emoción", "Salir con Solecita", "Comprar skin de pareja para los cascos",
    ]
    historial_chat = ""
    if history:
        for msg in history[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", msg.get("text", ""))[:500]
            historial_chat += f"\n{role.upper()}: {content}"
    task = f"""
Metas y planes con su novia (priorizar gastos de pareja): {", ".join(planes_pareja[:5])}...

""" + (f"HISTORIAL RECIENTE DEL CHAT:{historial_chat}\n\n" if historial_chat else "") + f"""
PREGUNTA ACTUAL DEL USUARIO:
\"\"\"{question}\"\"\"

Responde en ESPAÑOL, MARKDOWN. Incluye: 1) Resumen de su situación. 2) Análisis con números. 3) Presupuesto recomendado. 4) Oportunidades de ahorro. 5) Plan de acción. Termina con 📌 Acción inmediata: una cosa concreta."""
    prompt = SYSTEM_PROMPT_CFO + "\n\n" + master + "\n\n" + task
    model = get_gemini_model()
    response = model.generate_content(prompt)
    texto = response.text if hasattr(response, "text") else str(response)
    return {"advice": texto, "disponible": ctx["disponible"]}


def _build_daily_comparison(session: Session):
    """Comparación día a día: gastos esperados (fijos) vs reales del mes actual."""
    from datetime import date as _date
    today = _date.today()
    year, month = today.year, today.month
    stmt = select(Transaction).where(
        Transaction.date >= _date(year, month, 1),
        Transaction.date <= today,
    )
    transactions = list(session.exec(stmt).all())
    expected = [t for t in transactions if t.description and "fijo mensual" in (t.description or "")]
    real = [t for t in transactions if not (t.description and "fijo mensual" in (t.description or ""))]

    pareja_keywords = ["novia", "pareja", "ocio y pareja", "salida", "cine", "plan pareja"]

    def is_pareja(tx):
        cat = (tx.category or "").lower()
        concept = (tx.concept or "").lower()
        return any(k in cat or k in concept for k in pareja_keywords)

    lines = []
    for day in range(1, today.day + 1):
        d = _date(year, month, day)
        exp_gasto = sum(t.amount for t in expected if t.type == "gasto" and t.date == d)
        real_gasto = sum(t.amount for t in real if t.type == "gasto" and t.date == d)
        real_ingreso_d = sum(t.amount for t in real if t.type == "ingreso" and t.date == d)
        categories_real = list({t.category or "Otros" for t in real if t.type == "gasto" and t.date == d})
        tiene_pareja = any(is_pareja(t) for t in real if t.type == "gasto" and t.date == d)
        over = exp_gasto > 0 and real_gasto > exp_gasto
        lines.append(
            f"Día {day}: esperado {exp_gasto:,.0f} COP, real {real_gasto:,.0f} COP"
            + (f" (categorías: {', '.join(categories_real)})" if categories_real else "")
            + (" [incluye gastos pareja/novia]" if tiene_pareja else "")
            + (" [gastó más de lo previsto]" if over and exp_gasto else "")
        )
    return "\n".join(lines) if lines else "Aún no hay días con movimientos este mes."


@app.get("/api/advice/hints")
def get_advice_hints(session: Session = Depends(get_session)):
    """La IA compara día a día (esperado vs real), da alertas si te pasaste y mensajes contextuales (ej. gastos con novia)."""
    from datetime import date as _date
    stmt = select(Transaction)
    transactions = session.exec(stmt).all()
    transactions_expected = [
        t for t in transactions
        if t.description and "fijo mensual" in (t.description or "") and t.date <= _date.today()
    ]
    transactions_real = [
        t for t in transactions
        if not (t.description and "fijo mensual" in (t.description or ""))
    ]
    real_ingresos = sum(t.amount for t in transactions_real if t.type == "ingreso")
    real_gastos = sum(t.amount for t in transactions_real if t.type == "gasto")
    real_disponible = real_ingresos - real_gastos
    expected_gastos = sum(t.amount for t in transactions_expected if t.type == "gasto")
    balance = _get_savings_balance(session)
    goals = session.exec(select(Goal).order_by(Goal.id)).all()
    goals_str = ", ".join(f"{g.name} (meta {g.target_amount})" for g in goals) if goals else "Ninguno"
    daily_text = _build_daily_comparison(session)
    master = build_master_context(session)

    prompt = SYSTEM_PROMPT_CFO + "\n\n" + master + f"""

Tu rol en ESTA respuesta (hints breves):
1) Comparar día a día lo que la persona gastó vs lo previsto (fijos del mes).
2) Si algún día gastó MÁS de lo previsto: da una alerta breve y clara (ej. "El día X gastaste más de lo previsto").
3) Si va bien según lo previsto: dilo (ej. "Vas bien según lo previsto").
4) Si en algún día gastó más pero fue en salidas con la novia / Ocio y pareja: sé positivo y contextual (ej. "Saliste con tu novia y gastaron más ese día; está bien porque tenías presupuesto para gastos de pareja").

Datos del mes (solo movimientos reales, sin contar fijos en el resumen):
- Ingresos: {real_ingresos:,.0f} COP. Gastos: {real_gastos:,.0f} COP. Disponible: {real_disponible:,.0f} COP.
- Gastos esperados del mes (fijos): {expected_gastos:,.0f} COP.
- Ahorro actual: {balance:,.0f} COP. Objetivos: {goals_str}.

Comparación día a día (esperado vs real):
{daily_text}

Escribe 3 a 5 HINTS o frases cortas (una por línea): alertas si se pasó algún día, mensajes de "vas bien" cuando aplique, y mensajes contextuales si gastó más en pareja/novia. En español. Sin numerar ni títulos. Tono cercano."""
    try:
        model = get_gemini_model()
        r = model.generate_content(prompt)
        text = (r.text or "").strip() if hasattr(r, "text") else ""
        hints = [ln.strip() for ln in text.splitlines() if ln.strip()][:6]
        return {"hints": hints}
    except Exception:
        return {"hints": []}


CONTEXTO_PROMPT_BASE = """
CONTEXTO DEL USUARIO:
- Ingresos este mes: {ingresos:,.0f} COP
- Gastos este mes: {gastos:,.0f} COP
- Disponible: {disponible:,.0f} COP
- Tasa de ahorro actual: {tasa_ahorro}%
- Score financiero: {score}/100
- Ahorro en banco: {ahorro_banco:,.0f} COP
- Runway actual: {runway} días

HISTORIAL (últimos 3 meses):
{historial_json}

OBJETIVOS ACTIVOS:
{objetivos_json}

CATEGORÍAS ESTE MES vs PROMEDIO:
{anomalias_json}
"""

SYSTEM_PROMPT_CFO = """
Eres el CFO (Chief Financial Officer) personal del usuario.
Operas como si TUVIERAS TÚ MISMO ese dinero y fueras responsable de hacerlo crecer.

TU ROL:
- No eres un observador. Eres un tomador de decisiones.
- Hablas en primera persona del plural: "vamos a", "tenemos que", "esta semana hacemos".
- Conoces la situación completa: ingresos, gastos, objetivos, perfil personal, historial.
- Tu objetivo no es solo no gastar — es MAXIMIZAR el progreso hacia la visión del usuario.

TUS PRIORIDADES (en orden):
1. Cubrir compromisos fijos y necesidades básicas
2. Proteger el ahorro de emergencia (mínimo 3 meses de gastos)
3. Avanzar en objetivos prioritarios
4. Generar/escalar ingresos usando las habilidades disponibles
5. Calidad de vida razonable (ocio, pareja, experiencias)

CÓMO PIENSAS:
- Analiza el contexto completo antes de responder
- Si hay margen, di EXACTAMENTE a dónde va ese dinero
- Si hay problema, di EXACTAMENTE qué se recorta y cuánto
- Si hay oportunidad de ingreso (dada la ocupación/habilidades del usuario), la menciona
- Considera el contexto personal: relaciones, bienestar, no solo números

FORMATO DE RESPUESTA:
- Español natural y directo
- Markdown con secciones claras
- Números concretos en COP
- Máximo 300 palabras salvo que la pregunta requiera más
- Termina siempre con "📌 Acción inmediata:" + una sola cosa concreta a hacer hoy o esta semana
"""


@app.get("/api/advice/daily-briefing")
def get_daily_briefing(session: Session = Depends(get_session)):
    """Briefing matutino: 3 puntos clave del día (qué vigilar, fijos hoy, cómo va el score)."""
    ctx = _build_advice_context(session)
    from datetime import date as _date
    today = _date.today()
    stmt = select(Transaction).where(
        Transaction.date == today,
        Transaction.description.isnot(None),
    )
    txs_hoy = list(session.exec(stmt).all())
    fijos_hoy = [t for t in txs_hoy if t.description and "fijo mensual" in t.description]
    fijos_text = ", ".join(f"{t.concept or t.category}: ${t.amount:,.0f}" for t in fijos_hoy) if fijos_hoy else "Ninguno"
    master = build_master_context(session)
    task = f"""
Hoy es {today.strftime('%d/%m/%Y')}. Movimientos fijos programados para hoy: {fijos_text}.

Escribe un BRIEFING MATUTINO de exactamente 3 puntos cortos (bullets), en español:
1) Qué vigilar hoy (gastos, categorías en rojo, o algo positivo).
2) Si hay fijos hoy: recordatorio breve.
3) Cómo va su score y si está en camino de su meta de ahorro.

Responde SOLO los 3 bullets, sin título ni introducción. Máximo 2 líneas por bullet."""
    prompt = SYSTEM_PROMPT_CFO + "\n\n" + master + "\n\n" + task
    try:
        model = get_gemini_model()
        r = model.generate_content(prompt)
        text = (r.text or "").strip() if hasattr(r, "text") else ""
        bullets = [ln.strip() for ln in text.splitlines() if ln.strip()][:3]
        return {"bullets": bullets, "score": ctx["score"], "runway": ctx["runway"]}
    except Exception:
        return {"bullets": ["Revisa tus movimientos del día.", "Mantén el control de gastos.", "Cada ahorro cuenta."], "score": ctx["score"], "runway": ctx["runway"]}


@app.post("/api/advice/decision")
async def get_advice_decision(request: Request, session: Session = Depends(get_session)):
    """El usuario describe una decisión; la IA simula el impacto en sus números."""
    body = await request.json()
    decision = (body.get("decision") or body.get("question") or "").strip()
    if not decision:
        raise HTTPException(status_code=400, detail="Falta 'decision' o 'question'")
    ctx = _build_advice_context(session)
    prompt = CONTEXTO_PROMPT_BASE.format(**ctx) + f"""
El usuario está considerando esta decisión:
\"\"\"{decision}\"\"\"

Simula el impacto financiero: cómo afecta su disponible, ahorro, objetivos y runway. Da números concretos si puede estimar (ej. "Si compras X, tu disponible bajaría a Y"). Responde en español, MARKDOWN, máximo 15 líneas."""
    try:
        model = get_gemini_model()
        r = model.generate_content(prompt)
        texto = (r.text or "").strip() if hasattr(r, "text") else str(r)
        return {"advice": texto}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/advice/month-close")
def get_advice_month_close(session: Session = Depends(get_session)):
    """Análisis profundo de cierre de mes: qué pasó, por qué, plan para el siguiente."""
    ctx = _build_advice_context(session)
    prompt = CONTEXTO_PROMPT_BASE.format(**ctx) + """
Es el cierre del mes. Como asesor financiero, escribe un ANÁLISIS DE CIERRE en español con MARKDOWN:
1) Resumen: qué pasó este mes (ingresos, gastos, disponible, score).
2) Por qué: categorías que más pesaron o mejoraron.
3) Plan concreto para el próximo mes: 3-5 acciones específicas con números (ej. "Recortar Ocio en $50.000").
Máximo 20 líneas."""
    try:
        model = get_gemini_model()
        r = model.generate_content(prompt)
        texto = (r.text or "").strip() if hasattr(r, "text") else str(r)
        return {"advice": texto}
    except Exception:
        return {"advice": "No se pudo generar el análisis. Revisa tus datos del mes."}


@app.get("/api/advice/cfo-plan")
def get_cfo_plan(session: Session = Depends(get_session)):
    """El CFO revisa todo el contexto y genera un plan maestro para el mes."""
    context = build_master_context(session)
    prompt = context + """
=== TU TAREA ===
Genera el plan financiero maestro para este mes. Estructura tu respuesta así:

## 💰 Asignación del dinero disponible
[Dime exactamente a dónde va cada peso del disponible]

## 🎯 Estado de objetivos y próximos pasos
[Para cada objetivo: si está en track, cuánto apartar, de dónde]

## 📈 Oportunidades de ingreso
[Basado en las habilidades y ocupación del usuario, ¿qué puede hacer para generar más?]

## ⚠️ Riesgos y decisiones pendientes
[Qué puede salir mal, qué decisiones hay que tomar pronto]

## 📌 Acción inmediata
[Una sola cosa, concreta, que hacer esta semana]
"""
    try:
        model = get_gemini_model()
        r = model.generate_content(SYSTEM_PROMPT_CFO + "\n\n" + prompt)
        text = (r.text or "").strip() if hasattr(r, "text") else ""
        return {"plan": text or "No se pudo generar el plan. Revisa tu perfil y movimientos."}
    except Exception:
        return {"plan": "No se pudo conectar con el asesor. Intenta más tarde."}


@app.post("/api/advice/income-ideas")
def get_income_ideas(session: Session = Depends(get_session)):
    """La IA analiza el perfil y sugiere 3-5 formas concretas de aumentar ingresos en el corto plazo."""
    context = build_master_context(session)
    prompt = context + """
Basándote en las habilidades, ocupación y situación actual de esta persona,
sugiere 3-5 formas concretas y REALISTAS de generar ingresos adicionales
en los próximos 30-60 días.

Para cada idea:
- Nombre de la idea
- Por qué es viable para esta persona específica
- Cuánto podría generar (estimado conservador en COP)
- Primer paso concreto para empezar esta semana
- Esfuerzo requerido: bajo / medio / alto

Sé específico. No des consejos genéricos. Habla de SU situación.
"""
    try:
        model = get_gemini_model()
        r = model.generate_content(SYSTEM_PROMPT_CFO + "\n\n" + prompt)
        text = (r.text or "").strip() if hasattr(r, "text") else ""
        return {"ideas": text or "No se pudieron generar ideas. Completa tu perfil (ocupación, habilidades)."}
    except Exception:
        return {"ideas": "No se pudo conectar con el asesor. Intenta más tarde."}


@app.get("/api/advice/goal-strategy/{goal_id}")
def get_advice_goal_strategy(goal_id: int, session: Session = Depends(get_session)):
    """Estrategia específica para un objetivo: cuánto apartar, de qué recortar, fecha realista."""
    import finance_engine as fe
    goal = session.get(Goal, goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Objetivo no encontrado")
    ctx = _build_advice_context(session)
    ahorro_mensual = max(0, ctx["disponible"] * 0.2) if ctx["disponible"] else 0
    proy = fe.proyeccion_objetivo(
        goal.target_amount,
        ahorro_mensual,
        goal.deadline,
        goal.current_saved,
    )
    prompt = CONTEXTO_PROMPT_BASE.format(**ctx) + f"""
Objetivo: {goal.name}. Meta: ${goal.target_amount:,.0f}. Ahorrado: ${goal.current_saved:,.0f}. Frecuencia: {goal.frequency}. Fecha límite: {goal.deadline}.

Proyección calculada: {json.dumps(proy, ensure_ascii=False)}

Escribe una ESTRATEGIA ESPECÍFICA para este objetivo, en español, MARKDOWN:
1) Cuánto apartar cada semana o mes (número concreto).
2) De qué categoría recortar primero (usa las anomalías) y cuánto.
3) Fecha realista para cumplir la meta.
4) Un truco práctico (ej. "Aparta el mismo día que cobras"). Máximo 12 líneas."""
    try:
        model = get_gemini_model()
        r = model.generate_content(prompt)
        texto = (r.text or "").strip() if hasattr(r, "text") else str(r)
        return {"advice": texto, "proyeccion": proy}
    except Exception:
        return {"advice": "No se pudo generar la estrategia.", "proyeccion": proy}


@app.get("/api/categories")
def list_categories():
    """Lista fija de categorías analíticas (para dropdown y gráficas)."""
    return {"categories": CATEGORIAS_ANALITICAS}


@app.post("/api/autocategorize")
def autocategorize(
    amount: float = Form(...),
    description: str = Form(...),
):
    """IA elige UNA categoría de la lista fija (tiempo real). No crea nuevas."""
    try:
        cat = _pick_category_from_list((description or "").strip(), float(amount or 0))
        return {"category": cat}
    except Exception:
        return {"category": "Otros"}


@app.post("/api/parse-expenses-from-text")
async def parse_expenses_from_text(request: Request):
    """IA extrae gastos de un texto (voz transcrita o pegado). Devuelve lista {description, amount}."""
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Falta el texto")
    model = get_gemini_model()
    prompt = f"""El usuario dictó o pegó una lista de gastos. Extrae cada gasto como un ítem con descripción breve y monto en COP.
Texto del usuario:
\"\"\"{text}\"\"\"

Responde SOLO con una lista en formato JSON, un array de objetos, cada uno con exactamente: "description" (string, concepto del gasto) y "amount" (número, monto en pesos COP).
Ejemplo: [{{"description": "pan", "amount": 5000}}, {{"description": "café", "amount": 3000}}]
No incluyas explicaciones, solo el JSON array."""
    try:
        r = model.generate_content(prompt)
        raw = (r.text or "").strip()
        # Limpiar markdown si viene envuelto en ```
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        import json as _json
        items = _json.loads(raw)
        if not isinstance(items, list):
            items = []
        result = []
        for it in items:
            desc = (it.get("description") or it.get("desc") or "").strip()
            amt = it.get("amount") or it.get("monto") or 0
            try:
                amt = float(amt)
            except (TypeError, ValueError):
                amt = 0
            if desc:
                result.append({"description": desc, "amount": amt})
        return {"items": result}
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"No se pudo extraer gastos: {e}")


@app.post("/api/parse-expenses-from-image")
async def parse_expenses_from_image(
    file: UploadFile = File(...),
):
    """IA extrae gastos de una imagen de factura/recibo (vision)."""
    import base64
    file_bytes = await file.read()
    if not file_bytes or len(file_bytes) > 10 * 1024 * 1024:  # 10 MB
        raise HTTPException(status_code=400, detail="Imagen requerida (máx 10 MB)")
    model = get_gemini_model()
    # Determinar mime
    mime = file.content_type or "image/jpeg"
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        mime = "image/jpeg"
    b64 = base64.b64encode(file_bytes).decode("ascii")
    prompt = """Esta imagen es una factura o recibo de compra. Lista cada ítem o concepto con su monto en pesos (COP).
Responde SOLO con un JSON array de objetos, cada uno con: "description" (string, concepto) y "amount" (número, monto COP).
Ejemplo: [{"description": "pan", "amount": 5000}, {"description": "café", "amount": 3000}]
Sin explicaciones, solo el JSON array."""
    try:
        r = model.generate_content([
            {"inline_data": {"mime_type": mime, "data": b64}},
            prompt,
        ])
        raw = (r.text or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        import json as _json
        items = _json.loads(raw)
        if not isinstance(items, list):
            items = []
        result = []
        for it in items:
            desc = (it.get("description") or it.get("desc") or "").strip()
            amt = it.get("amount") or it.get("monto") or 0
            try:
                amt = float(amt)
            except (TypeError, ValueError):
                amt = 0
            if desc:
                result.append({"description": desc, "amount": amt})
        return {"items": result}
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"No se pudo leer la factura: {e}")


@app.get("/api/transactions/duplicate-check")
def duplicate_check(
    amount: float = 0,
    type: str = "gasto",
    session: Session = Depends(get_session),
):
    """Si existe una transacción reciente (este mes) con el mismo monto y tipo, posible duplicado."""
    from datetime import date as _date
    today = _date.today()
    stmt = (
        select(Transaction)
        .where(Transaction.date >= _date(today.year, today.month, 1))
        .where(Transaction.amount == amount)
        .where(Transaction.type == type)
    )
    txs = list(session.exec(stmt).all())
    return {"possible_duplicate": len(txs) >= 1, "count": len(txs)}


@app.get("/api/transactions", response_model=List[Transaction])
def list_transactions(session: Session = Depends(get_session)):
    stmt = select(Transaction).order_by(Transaction.date.desc())
    return session.exec(stmt).all()


@app.delete("/api/transactions/{tx_id}")
def delete_transaction(tx_id: int, session: Session = Depends(get_session)):
    tx = session.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    for li in session.exec(select(TransactionLineItem).where(TransactionLineItem.transaction_id == tx_id)).all():
        session.delete(li)
    session.delete(tx)
    session.commit()
    return {"ok": True}


@app.post("/api/transactions/remap-category")
async def remap_category(
    request: Request,
    session: Session = Depends(get_session),
):
    """Reasigna todas las transacciones con 'from_label' (concepto) a la categoría analítica 'to_label'."""
    body = await request.json()
    from_label = body.get("from_label") or body.get("from")
    to_label = body.get("to_label") or body.get("to")
    if not from_label or not to_label:
        raise HTTPException(status_code=400, detail="Se requieren from_label y to_label")
    if to_label not in CATEGORIAS_ANALITICAS:
        raise HTTPException(status_code=400, detail=f"to_label debe ser una de: {CATEGORIAS_ANALITICAS}")
    stmt = select(Transaction).where(Transaction.category == from_label)
    txs = list(session.exec(stmt).all())
    for tx in txs:
        tx.category = to_label
        tx.concept = from_label  # preservar el concepto
        session.add(tx)
    session.commit()
    return {"ok": True, "updated": len(txs)}


@app.put("/api/transactions/{tx_id}")
def update_transaction(
    tx_id: int,
    date_str: str = Form(...),
    amount: float = Form(...),
    type: str = Form(...),
    category: str = Form(...),
    description: str = Form(""),
    concept: str = Form(""),
    session: Session = Depends(get_session),
):
    from datetime import date as _date

    tx = session.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")

    try:
        tx.date = _date.fromisoformat(date_str)
        tx.amount = float(amount)
        tx.type = type
        tx.category = category
        tx.description = description or None
        tx.concept = concept.strip() or None
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error en datos: {exc}")

    session.add(tx)
    session.commit()
    session.refresh(tx)
    return tx


@app.patch("/api/transactions/{tx_id}")
def patch_transaction(
    tx_id: int,
    body: dict = Body(default_factory=dict),
    session: Session = Depends(get_session),
):
    """Actualización parcial: solo se modifican los campos enviados en el JSON (ej. category)."""
    tx = session.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")

    if "category" in body and body["category"] is not None:
        tx.category = str(body["category"]).strip() or tx.category
    if "date_str" in body and body["date_str"]:
        try:
            tx.date = date.fromisoformat(body["date_str"])
        except (ValueError, TypeError):
            pass
    if "amount" in body and body["amount"] is not None:
        try:
            tx.amount = float(body["amount"])
        except (ValueError, TypeError):
            pass
    if "type" in body and body["type"] in ("ingreso", "gasto"):
        tx.type = body["type"]
    if "description" in body:
        tx.description = body["description"] if body["description"] else None
    if "concept" in body:
        tx.concept = body["concept"].strip() if body.get("concept") else None

    session.add(tx)
    session.commit()
    session.refresh(tx)
    return tx


@app.get("/api/balance")
def get_balance(session: Session = Depends(get_session)):
    return {"balance": _get_savings_balance(session)}


@app.post("/api/balance")
def set_balance(
    balance: float = Form(...),
    session: Session = Depends(get_session),
):
    row = session.exec(select(SavingsBalance).limit(1)).first()
    if not row:
        row = SavingsBalance(balance=float(balance))
        session.add(row)
    else:
        row.balance = float(balance)
    session.commit()
    return {"balance": row.balance}


@app.get("/api/goals", response_model=List[Goal])
def list_goals(session: Session = Depends(get_session)):
    return session.exec(select(Goal).order_by(Goal.id)).all()


@app.post("/api/goals", response_model=Goal)
def create_goal(
    name: str = Form(...),
    target_amount: float = Form(...),
    frequency: str = Form("una_vez"),  # una_vez, mensual, anual
    deadline: str = Form(None),
    notes: str = Form(""),
    session: Session = Depends(get_session),
):
    from datetime import date as _date
    goal = Goal(
        name=name.strip(),
        target_amount=float(target_amount),
        frequency=frequency.strip() or "una_vez",
        deadline=_date.fromisoformat(deadline) if deadline else None,
        notes=notes.strip() or None,
    )
    session.add(goal)
    session.commit()
    session.refresh(goal)
    return goal


@app.put("/api/goals/{goal_id}", response_model=Goal)
def update_goal(
    goal_id: int,
    name: str = Form(None),
    target_amount: float = Form(None),
    frequency: str = Form(None),
    deadline: str = Form(None),
    current_saved: float = Form(None),
    notes: str = Form(None),
    session: Session = Depends(get_session),
):
    from datetime import date as _date
    goal = session.get(Goal, goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Objetivo no encontrado")
    if name is not None:
        goal.name = name.strip()
    if target_amount is not None:
        goal.target_amount = float(target_amount)
    if frequency is not None:
        goal.frequency = frequency.strip() or goal.frequency
    if deadline is not None:
        goal.deadline = _date.fromisoformat(deadline) if deadline else None
    if current_saved is not None:
        goal.current_saved = float(current_saved)
    if notes is not None:
        goal.notes = notes.strip() or None
    session.add(goal)
    session.commit()
    session.refresh(goal)
    return goal


@app.delete("/api/goals/{goal_id}")
def delete_goal(goal_id: int, session: Session = Depends(get_session)):
    goal = session.get(Goal, goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Objetivo no encontrado")
    session.delete(goal)
    session.commit()
    return {"ok": True}


@app.get("/objetivos", response_class=HTMLResponse)
def objetivos_page(request: Request, session: Session = Depends(get_session)):
    stmt = select(Transaction)
    transactions = session.exec(stmt).all()
    # Solo movimientos reales (sin fijos) para las tarjetas Ingresos / Gastos / Disponible
    transactions_real = [
        t for t in transactions
        if not (t.description and "fijo mensual" in (t.description or ""))
    ]
    ingresos = sum(t.amount for t in transactions_real if t.type == "ingreso")
    gastos = sum(t.amount for t in transactions_real if t.type == "gasto")
    disponible = ingresos - gastos
    balance = _get_savings_balance(session)
    goals = list(session.exec(select(Goal).order_by(Goal.id)).all())
    ahorro_mensual = max(0, disponible * 0.2) if disponible else 0
    import finance_engine as fe
    goal_projections = []
    for g in goals:
        proy = fe.proyeccion_objetivo(g.target_amount, ahorro_mensual, g.deadline, g.current_saved)
        goal_projections.append({"goal": g, "proyeccion": proy})
    goals_json = json.dumps([
        {"name": g.name, "deadline": g.deadline.isoformat() if g.deadline else None, "frequency": g.frequency, "target_amount": g.target_amount}
        for g in goals
    ])
    return templates.TemplateResponse(
        "objetivos.html",
        {
            "request": request,
            "ingresos": ingresos,
            "gastos": gastos,
            "disponible": disponible,
            "savings_balance": balance,
            "goals": goals,
            "goal_projections": goal_projections,
            "goals_json": goals_json,
            "theme": get_theme(session),
        },
    )


@app.get("/perfil", response_class=HTMLResponse)
def perfil_page(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse("perfil.html", {"request": request, "theme": get_theme(session)})


@app.get("/api/profile")
def get_profile(session: Session = Depends(get_session)):
    profile = session.exec(select(UserProfile).limit(1)).first()
    if not profile:
        return {
            "nombre": "",
            "edad": None,
            "ciudad": "",
            "ocupacion": "",
            "situacion_actual": "",
            "fuentes_ingreso": "",
            "habilidades": "",
            "restricciones": "",
            "vision": "",
            "tolerancia_riesgo": "moderado",
            "contexto_personal": "",
            "updated_at": None,
        }
    return {
        "id": profile.id,
        "nombre": profile.nombre or "",
        "edad": profile.edad,
        "ciudad": profile.ciudad or "",
        "ocupacion": profile.ocupacion or "",
        "situacion_actual": profile.situacion_actual or "",
        "fuentes_ingreso": profile.fuentes_ingreso or "",
        "habilidades": profile.habilidades or "",
        "restricciones": profile.restricciones or "",
        "vision": profile.vision or "",
        "tolerancia_riesgo": profile.tolerancia_riesgo or "moderado",
        "contexto_personal": profile.contexto_personal or "",
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


@app.post("/api/profile")
def save_profile(body: dict = Body(default_factory=dict), session: Session = Depends(get_session)):
    profile = session.exec(select(UserProfile).limit(1)).first()
    if not profile:
        profile = UserProfile()
        session.add(profile)
        session.flush()
    if "nombre" in body: profile.nombre = str(body.get("nombre") or "")[:200]
    if "edad" in body:
        v = body.get("edad")
        profile.edad = int(v) if v is not None and str(v).strip() != "" else None
    if "ciudad" in body: profile.ciudad = str(body.get("ciudad") or "")[:200]
    if "ocupacion" in body: profile.ocupacion = str(body.get("ocupacion") or "")[:200]
    if "situacion_actual" in body: profile.situacion_actual = str(body.get("situacion_actual") or "")[:2000]
    if "fuentes_ingreso" in body: profile.fuentes_ingreso = str(body.get("fuentes_ingreso") or "")[:2000]
    if "habilidades" in body: profile.habilidades = str(body.get("habilidades") or "")[:2000]
    if "restricciones" in body: profile.restricciones = str(body.get("restricciones") or "")[:2000]
    if "vision" in body: profile.vision = str(body.get("vision") or "")[:2000]
    if "tolerancia_riesgo" in body:
        v = str(body.get("tolerancia_riesgo") or "").strip().lower()
        if v in ("conservador", "moderado", "agresivo"): profile.tolerancia_riesgo = v
    if "contexto_personal" in body: profile.contexto_personal = str(body.get("contexto_personal") or "")[:2000]
    profile.updated_at = datetime.utcnow()
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return {"ok": True, "id": profile.id}


@app.get("/api/profile/completeness")
def profile_completeness(session: Session = Depends(get_session)):
    profile = session.exec(select(UserProfile).limit(1)).first()
    fields = [
        "nombre", "edad", "ciudad", "ocupacion", "situacion_actual",
        "fuentes_ingreso", "habilidades", "restricciones", "vision",
        "tolerancia_riesgo", "contexto_personal",
    ]
    total = len(fields)
    filled = 0
    if profile:
        for f in fields:
            v = getattr(profile, f, None)
            if v is not None and str(v).strip() != "":
                filled += 1
    percent = round((filled / total) * 100) if total else 0
    return {"percent": percent, "filled": filled, "total": total}


@app.get("/api/settings")
def get_settings(session: Session = Depends(get_session)):
    return {"theme": get_theme(session)}


@app.post("/api/settings")
def save_settings(body: dict = Body(default_factory=dict), session: Session = Depends(get_session)):
    if "theme" in body and body["theme"] in ("light", "dark"):
        set_theme(session, body["theme"])
    return {"theme": get_theme(session)}


@app.get("/analytics", response_class=HTMLResponse)
def analytics_page(request: Request, session: Session = Depends(get_session)):
    """Página de analítica: evolución mensual, patrón semanal, top gastos, proyección."""
    return templates.TemplateResponse("analytics.html", {"request": request, "theme": get_theme(session)})


@app.post("/api/advice/goals")
def get_advice_goals(
    question: str = Form(""),
    session: Session = Depends(get_session),
):
    master = build_master_context(session)
    goals = list(session.exec(select(Goal).order_by(Goal.id)).all())
    goals_data = [
        {"name": g.name, "target_amount": g.target_amount, "frequency": g.frequency, "deadline": str(g.deadline) if g.deadline else None, "current_saved": g.current_saved}
        for g in goals
    ]
    task = f"""
Objetivos que quiere cumplir: {goals_data}

IMPORTANTE: Si sus gastos son cercanos o mayores a sus ingresos, y su ahorro actual es bajo, está en riesgo. Sé muy claro y numérico.

Responde en español, con MARKDOWN. Incluye:
1) Si está realmente ahorrando o está consumiendo ahorros (y cuánto).
2) Cuánto puede destinar a cada objetivo por mes, con números concretos.
3) Orden sugerido para cumplir objetivos y plazos realistas.
4) Qué recortar o ajustar si no alcanza.
Termina con 📌 Acción inmediata: una cosa concreta.

Pregunta del usuario (opcional): \"\"\"{question or '¿Cuánto ahorrar para cada objetivo y cómo voy?'}\"\"\"
"""
    prompt = SYSTEM_PROMPT_CFO + "\n\n" + master + "\n\n" + task
    model = get_gemini_model()
    response = model.generate_content(prompt)
    texto = response.text if hasattr(response, "text") else str(response)
    return {"advice": texto}


@app.get("/api/analytics")
def get_analytics(session: Session = Depends(get_session)):
    """Analítica básica para gráficos: ingresos/gastos por día y gastos por categoría."""
    from datetime import date as _date

    today = _date.today()
    year, month = today.year, today.month

    stmt = select(Transaction).order_by(Transaction.date.asc())
    txs = session.exec(stmt).all()

    daily = {}
    category_gastos = {}

    for t in txs:
        if t.date.year == year and t.date.month == month:
            day = t.date.day
            if day not in daily:
                daily[day] = {"ingresos": 0.0, "gastos": 0.0}
            if t.type == "ingreso":
                daily[day]["ingresos"] += t.amount
            else:
                daily[day]["gastos"] += t.amount

        if t.type == "gasto":
            cat = t.category or "Otros"
            category_gastos[cat] = category_gastos.get(cat, 0.0) + t.amount

    daily_sorted = sorted(daily.items(), key=lambda x: x[0])
    labels = [str(d) for d, _ in daily_sorted]
    ingresos = [v["ingresos"] for _, v in daily_sorted]
    gastos = [v["gastos"] for _, v in daily_sorted]

    cat_labels = list(category_gastos.keys())
    cat_values = [category_gastos[c] for c in cat_labels]

    return {
        "daily": {
            "labels": labels,
            "ingresos": ingresos,
            "gastos": gastos,
        },
        "categorias_gasto": {
            "labels": cat_labels,
            "values": cat_values,
        },
        "categorias_analiticas": CATEGORIAS_ANALITICAS,
    }


# --- Sprint 1: Motor de riqueza (finance_engine + MonthSnapshot + analytics) ---

def _transacciones_reales_mes(session: Session, year: int, month: int):
    """Transacciones reales (sin fijo mensual) de un año/mes."""
    from datetime import date as _date
    first = _date(year, month, 1)
    last_day = monthrange(year, month)[1]
    last = _date(year, month, last_day)
    stmt = (
        select(Transaction)
        .where(Transaction.date >= first, Transaction.date <= last)
    )
    txs = list(session.exec(stmt).all())
    return [t for t in txs if not (t.description and "fijo mensual" in (t.description or ""))]


def _gastos_por_categoria(txs) -> dict:
    out = {}
    for t in txs:
        if t.type != "gasto":
            continue
        c = t.category or "Otros"
        out[c] = out.get(c, 0.0) + t.amount
    return out


def build_master_context(session: Session) -> str:
    """
    Construye el contexto completo que recibe la IA en cada llamada (estado del mundo del CFO personal).
    Incluye perfil de usuario, finanzas actuales, historial, objetivos y anomalías.
    """
    profile = session.exec(select(UserProfile).limit(1)).first()
    ctx = _build_advice_context(session)
    from datetime import datetime as _dt
    month_name = _dt.now().strftime("%B %Y")
    p = profile
    profile_block = f"""
=== QUIÉN SOY (PERFIL PERSONAL) ===
Nombre: {p.nombre if p else "No definido"}
Ocupación: {p.ocupacion if p else "No definida"}
Situación actual: {(p.situacion_actual or "No definida") if p else "No definida"}
Fuentes de ingreso: {(p.fuentes_ingreso or "No definidas") if p else "No definidas"}
Habilidades disponibles: {(p.habilidades or "No definidas") if p else "No definidas"}
Compromisos fijos: {(p.restricciones or "No definidos") if p else "No definidos"}
Visión a largo plazo: {(p.vision or "No definida") if p else "No definida"}
Tolerancia al riesgo: {p.tolerancia_riesgo if p else "moderado"}
Contexto personal: {(p.contexto_personal or "No definido") if p else "No definido"}
"""
    fixed = list(session.exec(select(FixedItem).order_by(FixedItem.day)).all())
    ingresos_fijos = [f for f in fixed if f.type == "ingreso"]
    gastos_fijos = [f for f in fixed if f.type == "gasto"]
    lineas_ing = [f"  Día {f.day}: {f.category} ${f.amount:,.0f} COP" for f in ingresos_fijos]
    lineas_gas = [f"  Día {f.day}: {f.category} ${f.amount:,.0f} COP" for f in gastos_fijos]
    total_ing_fijos = sum(f.amount for f in ingresos_fijos)
    total_gas_fijos = sum(f.amount for f in gastos_fijos)
    fixed_block = (
        "\n=== GASTOS E INGRESOS FIJOS (configuración del mes) ===\n"
        f"Ingresos fijos (total ${total_ing_fijos:,.0f} COP):\n"
        + ("\n".join(lineas_ing) if lineas_ing else "  Ninguno")
        + "\n\nGastos fijos (total ${:,.0f} COP):\n".format(total_gas_fijos)
        + ("\n".join(lineas_gas) if lineas_gas else "  Ninguno")
        + "\n\n"
    )
    return profile_block + fixed_block + f"""
=== ESTADO FINANCIERO ACTUAL ===
Mes en curso: {month_name}
Ingresos este mes: ${ctx["ingresos"]:,.0f} COP
Gastos este mes: ${ctx["gastos"]:,.0f} COP
Disponible: ${ctx["disponible"]:,.0f} COP
Tasa de ahorro: {ctx["tasa_ahorro"]:.1f}%
Score financiero: {ctx["score"]}/100
Runway estimado: {ctx["runway"]} días

=== HISTORIAL RECIENTE ===
{ctx["historial_json"]}

=== OBJETIVOS ACTIVOS ===
{ctx["objetivos_json"]}

=== ALERTAS DE CATEGORÍAS ===
{ctx["anomalias_json"]}
"""


def _build_advice_context(session: Session) -> dict:
    """Contexto enriquecido para todos los prompts de IA: score, runway, historial, objetivos, anomalías."""
    import finance_engine as fe
    from datetime import date as _date
    today = _date.today()
    txs = _transacciones_reales_mes(session, today.year, today.month)
    ingresos = sum(t.amount for t in txs if t.type == "ingreso")
    gastos = sum(t.amount for t in txs if t.type == "gasto")
    disponible = ingresos - gastos
    tasa_ahorro = fe.tasa_ahorro_real(ingresos, gastos)
    gasto_promedio_diario = gastos / today.day if today.day else 0
    runway = fe.calcular_runway(disponible, gasto_promedio_diario)
    balance = _get_savings_balance(session)
    goals = list(session.exec(select(Goal).order_by(Goal.id)).all())
    objetivos_json = json.dumps([
        {"name": g.name, "target_amount": g.target_amount, "frequency": g.frequency, "deadline": str(g.deadline) if g.deadline else None, "current_saved": g.current_saved}
        for g in goals
    ], ensure_ascii=False)
    snaps = session.exec(
        select(MonthSnapshot).order_by(MonthSnapshot.year.desc(), MonthSnapshot.month.desc()).limit(3)
    ).all()
    historial_json = json.dumps([
        {"year": s.year, "month": s.month, "ingresos": s.ingresos, "gastos": s.gastos, "disponible": s.disponible, "score": s.score_financiero}
        for s in reversed(snaps)
    ], ensure_ascii=False)
    gastos_mes = _gastos_por_categoria(txs)
    promedios = {}
    for i in range(1, 4):
        y, m = (today.year, today.month - i) if today.month - i >= 1 else (today.year - 1, today.month - i + 12)
        for c, val in _gastos_por_categoria(_transacciones_reales_mes(session, y, m)).items():
            promedios[c] = promedios.get(c, 0.0) + val
    for c in promedios:
        promedios[c] /= 3.0
    categorias_todas = set(gastos_mes.keys()) | set(promedios.keys())
    gastos_mes_completo = {c: gastos_mes.get(c, 0.0) for c in categorias_todas}
    anomalias = fe.categorias_anomalas(gastos_mes_completo, promedios)
    num_anomalas = sum(1 for a in anomalias if a["estado"] != "ok")
    score = fe.calcular_score_financiero(tasa_ahorro, num_anomalas, runway, 0, len(goals))
    anomalias_json = json.dumps([{"category": a["category"], "mes_actual": a["mes_actual"], "promedio": a["promedio"], "variacion_pct": a["variacion_pct"], "estado": a["estado"]} for a in anomalias], ensure_ascii=False)
    return {
        "ingresos": ingresos,
        "gastos": gastos,
        "disponible": disponible,
        "tasa_ahorro": tasa_ahorro,
        "score": score,
        "runway": runway,
        "ahorro_banco": balance,
        "historial_json": historial_json,
        "objetivos_json": objetivos_json,
        "anomalias_json": anomalias_json,
        "goals": goals,
    }


@app.post("/api/snapshots/generate")
def generate_snapshot(
    year: Optional[int] = None,
    month: Optional[int] = None,
    session: Session = Depends(get_session),
):
    """Genera el snapshot del mes indicado (o mes anterior si no se indica)."""
    import finance_engine as fe
    from datetime import date as _date
    today = _date.today()
    if year is None:
        year = today.year
    if month is None:
        # Por defecto: mes anterior
        if today.month == 1:
            year, month = today.year - 1, 12
        else:
            year, month = today.year, today.month - 1
    txs = _transacciones_reales_mes(session, year, month)
    ingresos = sum(t.amount for t in txs if t.type == "ingreso")
    gastos = sum(t.amount for t in txs if t.type == "gasto")
    disponible = ingresos - gastos
    tasa_ahorro = fe.tasa_ahorro_real(ingresos, gastos)
    gastos_por_cat = _gastos_por_categoria(txs)
    categoria_top = max(gastos_por_cat, key=gastos_por_cat.get) if gastos_por_cat else ""
    dias_mes = monthrange(year, month)[1]
    gasto_promedio_diario = gastos / dias_mes if dias_mes else 0
    runway = fe.calcular_runway(disponible, gasto_promedio_diario)
    goals = list(session.exec(select(Goal)).all())
    objetivos_en_track = 0  # simplificado: sin proyección por objetivo aquí
    score = fe.calcular_score_financiero(tasa_ahorro, 0, runway, objetivos_en_track, len(goals))
    existing = session.exec(
        select(MonthSnapshot).where(MonthSnapshot.year == year, MonthSnapshot.month == month)
    ).first()
    if existing:
        existing.ingresos = ingresos
        existing.gastos = gastos
        existing.disponible = disponible
        existing.tasa_ahorro = tasa_ahorro
        existing.score_financiero = score
        existing.categoria_top_gasto = categoria_top
        session.add(existing)
    else:
        session.add(
            MonthSnapshot(
                year=year,
                month=month,
                ingresos=ingresos,
                gastos=gastos,
                disponible=disponible,
                tasa_ahorro=tasa_ahorro,
                score_financiero=score,
                categoria_top_gasto=categoria_top,
            )
        )
    notif_msg = f"Resumen de {month:02d}/{year} guardado. Revisa Analytics."
    session.add(Notification(message=notif_msg, type="info", read=False))
    session.commit()
    return {"ok": True, "year": year, "month": month}


@app.get("/api/notifications")
def list_notifications(
    unread_only: bool = False,
    limit: int = 20,
    session: Session = Depends(get_session),
):
    """Lista notificaciones; por defecto las más recientes."""
    stmt = select(Notification).order_by(Notification.created_at.desc()).limit(limit)
    if unread_only:
        stmt = stmt.where(Notification.read == False)
    notifs = session.exec(stmt).all()
    return {
        "notifications": [
            {"id": n.id, "message": n.message, "type": n.type, "read": n.read, "created_at": n.created_at.isoformat() if n.created_at else None}
            for n in notifs
        ],
        "unread_count": len(session.exec(select(Notification).where(Notification.read == False)).all()),
    }


@app.put("/api/notifications/{nid}/read")
def mark_notification_read(nid: int, session: Session = Depends(get_session)):
    n = session.get(Notification, nid)
    if not n:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    n.read = True
    session.add(n)
    session.commit()
    return {"ok": True}


@app.get("/api/snapshots")
def list_snapshots(session: Session = Depends(get_session)):
    """Lista snapshots históricos, más recientes primero."""
    stmt = select(MonthSnapshot).order_by(MonthSnapshot.year.desc(), MonthSnapshot.month.desc())
    snaps = session.exec(stmt).all()
    return {
        "snapshots": [
            {
                "id": s.id,
                "year": s.year,
                "month": s.month,
                "ingresos": s.ingresos,
                "gastos": s.gastos,
                "disponible": s.disponible,
                "tasa_ahorro": s.tasa_ahorro,
                "score_financiero": s.score_financiero,
                "categoria_top_gasto": s.categoria_top_gasto,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in snaps
        ]
    }


@app.get("/api/analytics/score")
def get_analytics_score(session: Session = Depends(get_session)):
    """Score financiero actual + histórico (últimos snapshots)."""
    import finance_engine as fe
    from datetime import date as _date
    today = _date.today()
    txs = _transacciones_reales_mes(session, today.year, today.month)
    ingresos = sum(t.amount for t in txs if t.type == "ingreso")
    gastos = sum(t.amount for t in txs if t.type == "gasto")
    disponible = ingresos - gastos
    tasa_ahorro = fe.tasa_ahorro_real(ingresos, gastos)
    dias_mes = monthrange(today.year, today.month)[1]
    gasto_promedio_diario = gastos / today.day if today.day else 0
    runway = fe.calcular_runway(disponible, gasto_promedio_diario)
    goals = list(session.exec(select(Goal)).all())
    score_actual = fe.calcular_score_financiero(tasa_ahorro, 0, runway, 0, len(goals))
    snaps = session.exec(
        select(MonthSnapshot).order_by(MonthSnapshot.year.desc(), MonthSnapshot.month.desc()).limit(6)
    ).all()
    historial = [{"year": s.year, "month": s.month, "score": s.score_financiero} for s in snaps]
    score_anterior = snaps[0].score_financiero if snaps else None
    return {
        "score": score_actual,
        "tasa_ahorro": tasa_ahorro,
        "runway_dias": runway,
        "disponible": disponible,
        "ingresos": ingresos,
        "gastos": gastos,
        "historial": historial,
        "vs_mes_anterior": (score_actual - score_anterior) if score_anterior is not None else None,
    }


@app.get("/api/analytics/category-semaphore")
def get_analytics_category_semaphore(session: Session = Depends(get_session)):
    """Semáforo por categoría: este mes vs promedio últimos 3 meses."""
    import finance_engine as fe
    from datetime import date as _date
    today = _date.today()
    gastos_mes = _gastos_por_categoria(_transacciones_reales_mes(session, today.year, today.month))
    promedios = {}
    for i in range(1, 4):
        if today.month - i >= 1:
            y, m = today.year, today.month - i
        else:
            y, m = today.year - 1, today.month - i + 12
        txs = _transacciones_reales_mes(session, y, m)
        for c, val in _gastos_por_categoria(txs).items():
            promedios[c] = promedios.get(c, 0.0) + val
    for c in promedios:
        promedios[c] /= 3.0
    categorias_todas = set(gastos_mes.keys()) | set(promedios.keys())
    gastos_mes_completo = {c: gastos_mes.get(c, 0.0) for c in categorias_todas}
    anomalas = fe.categorias_anomalas(gastos_mes_completo, promedios)
    return {
        "categorias": [
            {
                "category": a["category"],
                "mes_actual": a["mes_actual"],
                "promedio": a["promedio"],
                "variacion_pct": a["variacion_pct"],
                "estado": a["estado"],
            }
            for a in anomalas
        ],
        "categorias_analiticas": CATEGORIAS_ANALITICAS,
    }


@app.get("/api/analytics/month-projection")
def get_analytics_month_projection(session: Session = Depends(get_session)):
    """Proyección de gastos a fin de mes si sigues al ritmo actual."""
    import finance_engine as fe
    from datetime import date as _date
    today = _date.today()
    txs = _transacciones_reales_mes(session, today.year, today.month)
    gastos = sum(t.amount for t in txs if t.type == "gasto")
    dias_mes = monthrange(today.year, today.month)[1]
    proy = fe.proyeccion_fin_mes(gastos, today.day, dias_mes)
    ingresos = sum(t.amount for t in txs if t.type == "ingreso")
    return {
        **proy,
        "ingresos_mes_actual": ingresos,
        "disponible_proyectado": ingresos - proy["proyeccion_fin_mes"] if ingresos else 0,
    }


@app.get("/api/analytics/monthly-evolution")
def get_analytics_monthly_evolution(session: Session = Depends(get_session)):
    """Datos últimos 6 meses (MonthSnapshot) para gráfico evolución."""
    snaps = session.exec(
        select(MonthSnapshot).order_by(MonthSnapshot.year.desc(), MonthSnapshot.month.desc()).limit(6)
    ).all()
    snaps = list(reversed(snaps))
    return {
        "labels": [f"{s.year}-{s.month:02d}" for s in snaps],
        "ingresos": [s.ingresos for s in snaps],
        "gastos": [s.gastos for s in snaps],
        "disponible": [s.disponible for s in snaps],
        "score": [s.score_financiero for s in snaps],
    }


@app.get("/api/analytics/weekly-pattern")
def get_analytics_weekly_pattern(session: Session = Depends(get_session)):
    """Patrón de gasto por día de la semana (0=lun, 6=dom)."""
    import finance_engine as fe
    from datetime import date as _date
    today = _date.today()
    txs = _transacciones_reales_mes(session, today.year, today.month)
    patron = fe.patron_semanal(txs)
    return {
        "por_dia": patron,
        "labels": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"],
    }


@app.get("/api/analytics/top-expenses")
def get_analytics_top_expenses(
    limit: int = 10,
    session: Session = Depends(get_session),
):
    """Top N gastos del mes por monto (solo reales)."""
    from datetime import date as _date
    today = _date.today()
    txs = [t for t in _transacciones_reales_mes(session, today.year, today.month) if t.type == "gasto"]
    txs.sort(key=lambda t: t.amount, reverse=True)
    top = txs[:limit]
    return {
        "items": [
            {
                "id": t.id,
                "date": t.date.isoformat(),
                "concept": t.concept or t.category,
                "category": t.category,
                "amount": t.amount,
            }
            for t in top
        ]
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
