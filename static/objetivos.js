// Balance: editar y guardar
const balanceDisplay = document.getElementById("balance-display");
const editBalanceBtn = document.getElementById("edit-balance");
const balanceForm = document.getElementById("balance-form");
const balanceInput = document.getElementById("balance-input");
const saveBalanceBtn = document.getElementById("save-balance");

if (editBalanceBtn) {
  editBalanceBtn.addEventListener("click", () => {
    balanceForm.classList.remove("hidden");
  });
}

if (saveBalanceBtn && balanceInput) {
  saveBalanceBtn.addEventListener("click", async () => {
    const val = balanceInput.value.trim();
    if (!val) return;
    try {
      const fd = new FormData();
      fd.append("balance", val);
      const res = await fetch("/api/balance", { method: "POST", body: fd });
      if (!res.ok) return;
      const data = await res.json();
      if (balanceDisplay) {
        balanceDisplay.textContent = "$" + Number(data.balance).toLocaleString("es-CO", { maximumFractionDigits: 0 });
      }
      balanceForm.classList.add("hidden");
      balanceInput.value = "";
    } catch (e) {}
  });
}

// Agregar objetivo
const goalForm = document.getElementById("goal-form");
if (goalForm) {
  goalForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(goalForm);
    try {
      const res = await fetch("/api/goals", { method: "POST", body: fd });
      if (res.ok) window.location.reload();
    } catch (e) {}
  });
}

// Borrar objetivo
document.querySelectorAll(".delete-goal").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const id = btn.dataset.goalId;
    if (!id || !window.confirm("¿Borrar este objetivo?")) return;
    try {
      const res = await fetch("/api/goals/" + id, { method: "DELETE" });
      if (res.ok) window.location.reload();
    } catch (e) {}
  });
});

// Ver estrategia IA por objetivo
document.querySelectorAll(".btn-strategy").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const id = btn.dataset.goalId;
    if (!id) return;
    const out = document.getElementById("strategy-" + id);
    if (!out) return;
    if (out.classList.contains("hidden")) {
      out.textContent = "Cargando…";
      out.classList.remove("hidden");
      try {
        const res = await fetch("/api/advice/goal-strategy/" + id);
        const data = await res.ok ? res.json() : {};
        if (window.marked && data.advice) {
          out.innerHTML = window.marked.parse(data.advice);
        } else {
          out.textContent = data.advice || "No se pudo cargar.";
        }
      } catch (e) {
        out.textContent = "Error al cargar.";
      }
    } else {
      out.classList.add("hidden");
      out.innerHTML = "";
    }
  });
});

// IA objetivos
const goalsAdviceForm = document.getElementById("goals-advice-form");
const goalsQuestion = document.getElementById("goals-question");
const goalsAdviceOutput = document.getElementById("goals-advice-output");
const goalsAdviceText = document.getElementById("goals-advice-text");

// Calendario de objetivos
(function renderGoalsCalendar() {
  const container = document.getElementById("goals-calendar");
  const goals = window.GOALS_FOR_CALENDAR || [];
  if (!container) return;

  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const first = new Date(year, month, 1);
  const last = new Date(year, month + 1, 0);
  const daysInMonth = last.getDate();
  const startWeekday = first.getDay();

  const weekdays = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"];
  const monthNames = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

  let html = '<div class="cal-header">' + monthNames[month] + ' ' + year + '</div>';
  html += '<div class="cal-weekdays">' + weekdays.map((w) => '<span>' + w + '</span>').join("") + "</div>";
  html += '<div class="cal-grid">';

  const goalsByDay = {};
  goals.forEach((g) => {
    if (g.deadline) {
      const d = g.deadline.slice(0, 10);
      if (!goalsByDay[d]) goalsByDay[d] = [];
      goalsByDay[d].push(g);
    }
  });

  for (let i = 0; i < startWeekday; i++) {
    html += '<div class="cal-day cal-empty"></div>';
  }
  for (let d = 1; d <= daysInMonth; d++) {
    const key = year + "-" + String(month + 1).padStart(2, "0") + "-" + String(d).padStart(2, "0");
    const dayGoals = goalsByDay[key] || [];
    const hasGoal = dayGoals.length > 0;
    html += '<div class="cal-day' + (hasGoal ? ' cal-has-goal' : '') + '">';
    html += '<span class="cal-num">' + d + "</span>";
    dayGoals.forEach((g) => {
      const name = (g.name || "").replace(/"/g, "&quot;");
      const short = name.length > 12 ? name.slice(0, 11) + "…" : name;
      html += '<span class="cal-goal" title="' + name + '">' + short + "</span>";
    });
    html += "</div>";
  }

  html += "</div>";
  container.innerHTML = '<div class="goals-calendar-wrap"><div class="goals-calendar">' + html + "</div></div>";
})();

if (goalsAdviceForm) {
  goalsAdviceForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    goalsAdviceOutput.classList.remove("hidden");
    goalsAdviceText.textContent = "Pensando...";
    try {
      const fd = new FormData();
      fd.append("question", goalsQuestion.value.trim());
      const res = await fetch("/api/advice/goals", { method: "POST", body: fd });
      if (!res.ok) throw new Error();
      const data = await res.json();
      if (window.marked) {
        goalsAdviceText.innerHTML = window.marked.parse(data.advice || "");
      } else {
        goalsAdviceText.textContent = data.advice || "";
      }
    } catch (err) {
      goalsAdviceText.textContent = "No se pudo obtener la respuesta. Revisa el servidor.";
    }
  });
}
