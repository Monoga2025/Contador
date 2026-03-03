"""
Motor de análisis financiero para LuxFinance.
Alimenta métricas, proyecciones y toda la IA.
"""
from datetime import date, timedelta
from typing import Dict, List, Any, Optional


def calcular_runway(disponible_mes: float, gasto_promedio_diario: float) -> int:
    """
    Cuántos días puede vivir el usuario con lo que tiene disponible este mes.
    Si gasto_promedio_diario es 0, retorna 999 (ilimitado simbólico).
    """
    if gasto_promedio_diario is None or gasto_promedio_diario <= 0:
        return 999 if disponible_mes and disponible_mes > 0 else 0
    if disponible_mes is None or disponible_mes <= 0:
        return 0
    return max(0, int(disponible_mes / gasto_promedio_diario))


def tasa_ahorro_real(ingresos: float, gastos: float) -> float:
    """
    Porcentaje real ahorrado (0-100). Meta saludable: 20%+.
    Si ingresos <= 0 retorna 0.
    """
    if ingresos is None or ingresos <= 0:
        return 0.0
    gastos = gastos or 0
    disponible = ingresos - gastos
    if disponible <= 0:
        return 0.0
    return round((disponible / ingresos) * 100.0, 1)


def categorias_anomalas(
    gastos_mes_actual: Dict[str, float],
    gastos_promedio_3_meses: Dict[str, float],
    umbral_porcentaje: float = 30.0,
) -> List[Dict[str, Any]]:
    """
    Categorías que superan en más de umbral_porcentaje (default 30%) su promedio histórico.
    Retorna lista de { "category", "mes_actual", "promedio", "variacion_pct", "estado" }.
    estado: "ok" | "amarillo" (15-30%) | "rojo" (>30%).
    """
    resultado = []
    for cat, actual in gastos_mes_actual.items():
        actual = actual or 0
        promedio = gastos_promedio_3_meses.get(cat) or 0
        if promedio <= 0:
            if actual > 0:
                resultado.append({
                    "category": cat,
                    "mes_actual": actual,
                    "promedio": 0,
                    "variacion_pct": 100.0,
                    "estado": "rojo",
                })
            continue
        variacion = ((actual - promedio) / promedio) * 100.0
        if variacion >= umbral_porcentaje:
            estado = "rojo"
        elif variacion >= 15.0:
            estado = "amarillo"
        else:
            estado = "ok"
        resultado.append({
            "category": cat,
            "mes_actual": actual,
            "promedio": promedio,
            "variacion_pct": round(variacion, 1),
            "estado": estado,
        })
    return resultado


def proyeccion_objetivo(
    meta: float,
    ahorro_mensual_disponible: float,
    fecha_limite: Optional[date],
    current_saved: float = 0.0,
) -> Dict[str, Any]:
    """
    ¿Alcanza la meta? Cuánto falta. Qué ajuste necesita.
    Retorna: alcanza (bool), falta (float), meses_restantes (int|None),
    necesario_mensual (float), mensaje_ajuste (str).
    """
    falta = max(0, meta - (current_saved or 0))
    if falta <= 0:
        return {
            "alcanza": True,
            "falta": 0,
            "meses_restantes": 0,
            "necesario_mensual": 0,
            "mensaje_ajuste": "Meta alcanzada.",
            "con_ritmo_actual_llega": None,
            "recorte_sugerido": 0,
        }
    if fecha_limite:
        hoy = date.today()
        if fecha_limite <= hoy:
            meses_restantes = 0
        else:
            meses_restantes = max(0, (fecha_limite.year - hoy.year) * 12 + (fecha_limite.month - hoy.month))
            if fecha_limite.day > hoy.day:
                meses_restantes += 1
    else:
        meses_restantes = None

    meses_estimados = None
    if meses_restantes is not None and meses_restantes > 0:
        necesario_mensual = falta / meses_restantes
        alcanza = (ahorro_mensual_disponible or 0) >= necesario_mensual
        recorte = max(0, necesario_mensual - (ahorro_mensual_disponible or 0)) if not alcanza else 0
        if alcanza:
            mensaje = f"Con ${ahorro_mensual_disponible:,.0f}/mes alcanzas la meta a tiempo."
        else:
            mensaje = f"Necesitas apartar ${necesario_mensual:,.0f}/mes. Te faltan ${recorte:,.0f}/mes."
    else:
        necesario_mensual = ahorro_mensual_disponible or 0
        if necesario_mensual <= 0:
            mensaje = "Define una fecha límite o aumenta tu ahorro mensual para ver proyección."
        else:
            meses_estimados = max(1, int(falta / necesario_mensual))
            mensaje = f"Con ${necesario_mensual:,.0f}/mes llegarías en ~{meses_estimados} meses."
        alcanza = False
        recorte = max(0, falta - (ahorro_mensual_disponible or 0))
        meses_restantes = meses_restantes if meses_restantes is not None else meses_estimados

    nec_final = necesario_mensual if (meses_restantes and meses_restantes > 0) else (falta / max(1, meses_restantes or 1))
    return {
        "alcanza": alcanza,
        "falta": falta,
        "meses_restantes": meses_restantes,
        "necesario_mensual": nec_final,
        "mensaje_ajuste": mensaje,
        "con_ritmo_actual_llega": meses_estimados if not fecha_limite and (ahorro_mensual_disponible or 0) > 0 else None,
        "recorte_sugerido": recorte,
    }


def calcular_score_financiero(
    tasa_ahorro: float,
    num_categorias_anomalas: int,
    runway_dias: int,
    objetivos_en_track: int,
    total_objetivos: int = 0,
) -> int:
    """
    Score de salud financiera 0-100.
    Factores: tasa de ahorro (meta 20%+), categorías fuera de control, runway, objetivos al día.
    """
    score = 50  # base
    # Tasa ahorro: 20%+ = bueno, 10-20 = regular, <10 = malo
    if tasa_ahorro >= 20:
        score += 15
    elif tasa_ahorro >= 10:
        score += 5
    elif tasa_ahorro >= 0:
        score -= 10
    # Categorías anómalas (rojas/amarillas): cada una resta
    score -= min(20, num_categorias_anomalas * 5)
    # Runway: 30+ días bien, 14-30 regular, <14 mal
    if runway_dias >= 30:
        score += 10
    elif runway_dias >= 14:
        score += 5
    elif runway_dias < 7 and runway_dias != 999:
        score -= 10
    # Objetivos en track
    if total_objetivos > 0 and objetivos_en_track == total_objetivos:
        score += 10
    elif total_objetivos > 0 and objetivos_en_track > 0:
        score += 5
    return max(0, min(100, score))


def patron_semanal(transacciones: List[Any]) -> Dict[str, float]:
    """
    Días de la semana donde más se gasta. Entrada: lista de objetos con .date y .amount y .type.
    Retorna dict dia_semana (0=lunes, 6=domingo) -> total gastos.
    """
    from datetime import datetime
    por_dia = {i: 0.0 for i in range(7)}  # 0 = lunes en isoweekday
    for t in transacciones or []:
        if getattr(t, "type", None) != "gasto":
            continue
        d = getattr(t, "date", None)
        if not d:
            continue
        if hasattr(d, "isoweekday"):
            # Monday=1 .. Sunday=7 -> 0=lunes, 6=domingo
            wd = (d.isoweekday() - 1) % 7
        else:
            wd = 0
        por_dia[wd] = por_dia.get(wd, 0) + float(getattr(t, "amount", 0) or 0)
    return por_dia


def proyeccion_fin_mes(gastos_acumulados: float, dia_del_mes: int, dias_del_mes: int) -> Dict[str, float]:
    """
    Si sigues a este ritmo, proyección de gastos al cierre del mes.
    Fórmula: (gastos_actuales / dia_del_mes) * dias_del_mes
    """
    if dia_del_mes is None or dia_del_mes <= 0:
        dia_del_mes = 1
    if dias_del_mes is None or dias_del_mes <= 0:
        dias_del_mes = 30
    gastos_acumulados = gastos_acumulados or 0
    ritmo_diario = gastos_acumulados / dia_del_mes if dia_del_mes else 0
    proyeccion = ritmo_diario * dias_del_mes if ritmo_diario else 0
    return {
        "gastos_acumulados": gastos_acumulados,
        "ritmo_diario": round(ritmo_diario, 0),
        "proyeccion_fin_mes": round(proyeccion, 0),
        "dia_actual": dia_del_mes,
        "dias_del_mes": dias_del_mes,
    }
