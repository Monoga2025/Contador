// Calendario: al hacer clic en el campo o su contenedor, abrir siempre el mini calendario (día/mes/año con lang=es)
(function setupDatePickerOpen() {
  document.addEventListener("click", function (e) {
    var wrap = e.target.closest("[data-open-date-picker]");
    if (!wrap) return;
    var input = wrap.querySelector('input[type="date"]');
    if (input) {
      input.focus();
      if (typeof input.showPicker === "function") input.showPicker();
    }
  });
})();

// Overlay de carga (IA procesando)
function showLoading() {
  var el = document.getElementById("loading-overlay");
  if (el) el.classList.remove("hidden");
}
function hideLoading() {
  var el = document.getElementById("loading-overlay");
  if (el) el.classList.add("hidden");
}
window.showLoading = showLoading;
window.hideLoading = hideLoading;

window.adviceHistory = [];
const form = document.getElementById("advice-form");
const questionEl = document.getElementById("question");
const adviceBox = document.getElementById("advice-output");
const adviceText = document.getElementById("advice-text");
const chatHistoryEl = document.getElementById("advice-chat-history");

if (form) {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const question = questionEl.value.trim();
    if (!question) return;

    adviceBox.classList.remove("hidden");
    adviceText.textContent = "Procesando…";
    if (chatHistoryEl) {
      var userDiv = document.createElement("div");
      userDiv.className = "chat-msg user";
      userDiv.textContent = question;
      chatHistoryEl.appendChild(userDiv);
    }
    window.adviceHistory.push({ role: "user", content: question });
    questionEl.value = "";

    showLoading();
    try {
      const res = await fetch("/api/advice", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question, history: window.adviceHistory.slice(-10) }),
      });

      if (!res.ok) throw new Error("Error pidiendo consejo a la IA");
      const data = await res.json();
      if (window.marked) {
        adviceText.innerHTML = window.marked.parse(data.advice || "");
      } else {
        adviceText.textContent = data.advice || "";
      }
      window.adviceHistory.push({ role: "assistant", content: data.advice || "" });
      if (chatHistoryEl) {
        var botDiv = document.createElement("div");
        botDiv.className = "chat-msg assistant";
        botDiv.innerHTML = (window.marked && data.advice ? window.marked.parse(data.advice) : data.advice) || "";
        chatHistoryEl.appendChild(botDiv);
      }
      var drawer = document.getElementById("ia-drawer");
      if (drawer) { drawer.classList.remove("hidden"); drawer.scrollTop = drawer.scrollHeight; }
    } catch (err) {
      adviceText.textContent = "No se pudo obtener consejo. Revisa el servidor o Gemini.";
    } finally {
      hideLoading();
    }
  });
}
document.querySelectorAll("#advice-chips .chip").forEach(function (btn) {
  btn.addEventListener("click", function () {
    var q = btn.getAttribute("data-question");
    if (questionEl) questionEl.value = q || "";
    if (questionEl) questionEl.focus();
  });
});
var btnPreguntale = document.getElementById("btn-preguntale");
if (btnPreguntale) {
  btnPreguntale.addEventListener("click", function () {
    if (iaDrawer) { iaDrawer.classList.remove("hidden"); if (questionEl) questionEl.focus(); }
  });
}

// Prefijar la fecha de hoy en todas las filas del registro rápido
function setTodayOnDateInputs() {
  const today = new Date();
  const iso = today.toISOString().slice(0, 10);
  document.querySelectorAll(".date-input-multi").forEach((el) => {
    if (!el.value) el.value = iso;
  });
}
setTodayOnDateInputs();

// Categoría en tiempo real por IA (elige de la lista fija)
function wireAutoCategorizeForRow(row) {
  const amountInput = row.querySelector('input[name="amount"]');
  const categorySelect = row.querySelector('select[name="category"]');
  const descriptionInput = row.querySelector('input[name="description"]');
  if (!categorySelect) return; // ya no hay categoría manual; la asigna la IA al guardar
  if (!amountInput || !descriptionInput) return;

  let debounceTimer = null;
  async function maybeAutoCategorize() {
    const amount = amountInput.value.trim();
    const description = descriptionInput.value.trim();
    if (!amount || !description) return;
    // Solo asignar si sigue en "— La IA la asigna en tiempo real —"
    if (categorySelect.value) return;

    try {
      const fd = new FormData();
      fd.append("amount", amount);
      fd.append("description", description);
      const res = await fetch("/api/autocategorize", { method: "POST", body: fd });
      if (!res.ok) return;
      const data = await res.json();
      if (data.category) {
        categorySelect.value = data.category;
      }
    } catch (e) {}
  }

  function debounced() {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(maybeAutoCategorize, 500);
  }

  descriptionInput.addEventListener("blur", maybeAutoCategorize);
  descriptionInput.addEventListener("input", debounced);
  amountInput.addEventListener("blur", maybeAutoCategorize);
  amountInput.addEventListener("input", debounced);
}

document.querySelectorAll(".quick-row").forEach(wireAutoCategorizeForRow);

// Botón "Agregar fila": clona la última fila usando misma fecha/tipo/categoría,
// pero limpia monto y descripción.
const addRowBtn = document.getElementById("add-row");
if (addRowBtn) {
  addRowBtn.addEventListener("click", () => {
    const tbody = document.querySelector(".quick-table tbody");
    if (!tbody) return;
    const rows = tbody.querySelectorAll(".quick-row");
    const last = rows[rows.length - 1];
    if (!last) return;

    const clone = last.cloneNode(true);

    const amountInput = clone.querySelector('input[name="amount"]');
    const descInput = clone.querySelector('input[name="description"]');
    const catHidden = clone.querySelector('input[name="category"]');
    if (amountInput) amountInput.value = "";
    if (descInput) descInput.value = "";
    if (catHidden) catHidden.value = "";

    clone.querySelectorAll("[id]").forEach((el) => el.removeAttribute("id"));
    var cb = clone.querySelector(".include-row-cb");
    if (cb) cb.checked = true;

    tbody.appendChild(clone);
    setTodayOnDateInputs();
    wireAutoCategorizeForRow(clone);
  });
}

// Envío del formulario rápido: solo filas con "Incluir" marcado
var quickForm = document.getElementById("quick-form");
if (quickForm) {
  quickForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var tbody = quickForm.querySelector(".quick-table tbody");
    if (!tbody) return;
    var rows = tbody.querySelectorAll(".quick-row");
    var fd = new FormData();
    var dateStr = [], amount = [], type = [], category = [], description = [];
    rows.forEach(function (row) {
      var cb = row.querySelector(".include-row-cb");
      if (cb && !cb.checked) return;
      var d = row.querySelector('input[name="date_str"]');
      var a = row.querySelector('input[name="amount"]');
      var t = row.querySelector('select[name="type"]');
      var c = row.querySelector('input[name="category"], select[name="category"]');
      var desc = row.querySelector('input[name="description"]');
      if (d) dateStr.push(d.value || "");
      if (a) amount.push(a.value || "");
      if (t) type.push(t.value || "gasto");
      if (c) category.push(c.value || "");
      if (desc) description.push(desc.value || "");
    });
    if (dateStr.length === 0) return;
    dateStr.forEach(function (v) { fd.append("date_str", v); });
    amount.forEach(function (v) { fd.append("amount", v); });
    type.forEach(function (v) { fd.append("type", v); });
    category.forEach(function (v) { fd.append("category", v); });
    description.forEach(function (v) { fd.append("description", v); });
    fetch(quickForm.action, { method: "POST", body: fd })
      .then(function (r) {
        if (r.ok || r.redirected) window.location.reload();
      })
      .catch(function () {});
  });
}

// Toggle del asesor IA
var toggleIaBtn = document.getElementById("toggle-ia");
var iaDrawer = document.getElementById("ia-drawer");
if (toggleIaBtn && iaDrawer) {
  toggleIaBtn.addEventListener("click", function () {
    iaDrawer.classList.toggle("hidden");
  });
}
document.querySelectorAll("[data-close-ia]").forEach(function (el) {
  el.addEventListener("click", function () {
    if (iaDrawer) iaDrawer.classList.add("hidden");
  });
});
var onboardingModal = document.getElementById("onboarding-modal");
document.querySelectorAll("[data-close-onboarding]").forEach(function (el) {
  el.addEventListener("click", function () {
    if (onboardingModal) { onboardingModal.classList.add("hidden"); onboardingModal.setAttribute("aria-hidden", "true"); }
  });
});

var btnEsperados = document.getElementById("btn-movimientos-esperados");
var drawerEsperados = document.getElementById("drawer-esperados");
if (btnEsperados && drawerEsperados) {
  btnEsperados.addEventListener("click", function () {
    drawerEsperados.classList.remove("hidden");
  });
}
document.querySelectorAll("[data-close-drawer=\"esperados\"]").forEach(function (el) {
  el.addEventListener("click", function () {
    if (drawerEsperados) drawerEsperados.classList.add("hidden");
  });
});

// Borrar movimientos reales (vista compacta: .delete-tx-compact)
(function setupDeleteTx() {
  function deleteTxHandler(btn) {
    return async function () {
      const id = btn.dataset.txId;
      if (!id) return;
      if (!window.confirm("¿Seguro que quieres borrar este movimiento?")) return;
      try {
        const res = await fetch("/api/transactions/" + id, { method: "DELETE" });
        if (res.ok) window.location.reload();
      } catch {}
    };
  }
  document.addEventListener("click", function (e) {
    const btn = e.target.closest(".delete-tx-compact, .delete-tx");
    if (btn) { e.preventDefault(); deleteTxHandler(btn)(); }
  });
})();

// Editar registro real: abrir modal y guardar con PUT
(function setupEditMovimientoModal() {
  const modal = document.getElementById("modal-editar-movimiento");
  const form = document.getElementById("form-editar-movimiento");
  if (!modal || !form) return;

  document.addEventListener("click", function (e) {
    const btn = e.target.closest(".edit-tx-compact, .edit-tx, .figma-mov-menu");
    if (!btn) return;
    e.preventDefault();
    const id = btn.dataset.txId;
    if (!id) return;
    document.getElementById("edit-tx-id").value = id;
    document.getElementById("edit-tx-date").value = btn.dataset.txDate || "";
    document.getElementById("edit-tx-amount").value = btn.dataset.txAmount != null ? btn.dataset.txAmount : "";
    document.getElementById("edit-tx-type").value = btn.dataset.txType || "gasto";
    document.getElementById("edit-tx-category").value = btn.dataset.txCategory || "Otros";
    document.getElementById("edit-tx-concept").value = btn.dataset.txConcept || "";
    document.getElementById("edit-tx-description").value = btn.dataset.txDescription || "";
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
  });

  function closeModal() {
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
  }
  modal.querySelectorAll("[data-close-modal=\"editar-mov\"]").forEach(function (el) {
    el.addEventListener("click", closeModal);
  });

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const id = document.getElementById("edit-tx-id").value;
    if (!id) return;
    const fd = new FormData();
    fd.append("date_str", document.getElementById("edit-tx-date").value);
    fd.append("amount", document.getElementById("edit-tx-amount").value);
    fd.append("type", document.getElementById("edit-tx-type").value);
    fd.append("category", document.getElementById("edit-tx-category").value);
    fd.append("concept", document.getElementById("edit-tx-concept").value);
    fd.append("description", document.getElementById("edit-tx-description").value);
    try {
      const res = await fetch("/api/transactions/" + id, { method: "PUT", body: fd });
      if (res.ok) { closeModal(); window.location.reload(); }
    } catch {}
  });
})();

// Filtros: vista compacta (.mov-line dentro de .mov-day-group)
(function setupFilterMovimientos() {
  const btnToggleFilters = document.getElementById("btn-toggle-filters");
  const panelFiltros = document.getElementById("filters-panel");
  const filtroCategoria = document.getElementById("filtro-categoria");
  const filtroTipo = document.getElementById("filtro-tipo");
  const btnAplicar = document.getElementById("filtro-aplicar");
  const wrap = document.querySelector(".movimientos-compact-wrap");
  if (!btnToggleFilters || !panelFiltros || !wrap) return;

  btnToggleFilters.addEventListener("click", function () {
    panelFiltros.classList.toggle("open");
    this.classList.toggle("active");
  });

  function applyFilter() {
    const cat = (filtroCategoria && filtroCategoria.value) || "";
    const tipo = (filtroTipo && filtroTipo.value) || "";
    const lines = wrap.querySelectorAll(".mov-line:not(.mov-subdetail)");
    const groups = wrap.querySelectorAll(".mov-day-group");
    lines.forEach(function (li) {
      const rowCat = (li.dataset.txCategory || "").trim();
      const rowTipo = (li.dataset.txType || "").trim();
      const show = (!cat || rowCat === cat) && (!tipo || rowTipo === tipo);
      li.style.display = show ? "" : "none";
      var next = li.nextElementSibling;
      if (next && next.classList.contains("mov-subdetail")) next.style.display = show ? "" : "none";
    });
    groups.forEach(function (gr) {
      const mainLines = gr.querySelectorAll(".mov-line:not(.mov-subdetail)");
      const visible = Array.from(mainLines).filter(function (el) { return el.style.display !== "none"; }).length;
      gr.style.display = visible > 0 ? "" : "none";
    });
  }

  if (btnAplicar) btnAplicar.addEventListener("click", applyFilter);
})();

// Ordenar movimientos por fecha: reordenar .mov-day-group
let sortAsc = false;
(function setupSortMovimientos() {
  const btnSort = document.getElementById("btn-toggle-sort");
  const wrap = document.querySelector(".movimientos-compact-wrap");
  if (!btnSort || !wrap) return;

  window.sortTransactionsTable = function (asc) {
    const groups = Array.from(wrap.querySelectorAll(".mov-day-group"));
    groups.sort(function (a, b) {
      const dateA = (a.dataset.date || "").trim();
      const dateB = (b.dataset.date || "").trim();
      if (!dateA || !dateB) return 0;
      if (dateA < dateB) return asc ? -1 : 1;
      if (dateA > dateB) return asc ? 1 : -1;
      return 0;
    });
    groups.forEach(function (g) { wrap.appendChild(g); });
  };

  btnSort.addEventListener("click", function () {
    sortAsc = !sortAsc;
    this.classList.toggle("active", !sortAsc);
    window.sortTransactionsTable(sortAsc);
  });
})();

// Categoría inline (por si se vuelve a usar tabla con .category-select)
async function updateCategory(selectEl) {
  const txId = selectEl.dataset.transactionId;
  const newCategory = selectEl.value;
  if (!txId) return;
  selectEl.classList.add("saving");
  selectEl.classList.remove("saved", "error");
  try {
    const res = await fetch("/api/transactions/" + txId, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ category: newCategory }) });
    if (res.ok) {
      var tr = selectEl.closest("tr");
      if (tr) tr.dataset.txCategory = newCategory;
      selectEl.classList.remove("saving"); selectEl.classList.add("saved");
      setTimeout(function () { selectEl.classList.remove("saved"); }, 1500);
    } else { selectEl.classList.remove("saving"); selectEl.classList.add("error"); }
  } catch (e) { selectEl.classList.remove("saving"); selectEl.classList.add("error"); }
}
document.querySelectorAll(".category-select").forEach(function (sel) {
  sel.addEventListener("change", function () { updateCategory(this); });
});

// Gráficos de analítica
let pieChartInstance = null;

async function initCharts() {
  const lineCanvas = document.getElementById("line-chart");
  const pieCanvas = document.getElementById("pie-chart");
  if (!lineCanvas || !pieCanvas || !window.Chart) return;

  try {
    const res = await fetch("/api/analytics");
    if (!res.ok) return;
    const data = await res.json();

    const daily = data.daily || { labels: [], ingresos: [], gastos: [] };
    const cat = data.categorias_gasto || { labels: [], values: [] };

    // FIX: Colores de gráficos desde design system (--lux-success, --lux-danger)
    var style = getComputedStyle(document.documentElement);
    var colorIngreso = style.getPropertyValue("--lux-success").trim() || "#22c55e";
    var colorGasto = style.getPropertyValue("--lux-danger").trim() || "#ef4444";

    new window.Chart(lineCanvas.getContext("2d"), {
      type: "line",
      data: {
        labels: daily.labels,
        datasets: [
          {
            label: "Ingresos",
            data: daily.ingresos,
            borderColor: colorIngreso,
            backgroundColor: "rgba(34, 197, 94, 0.2)",
            tension: 0.3,
          },
          {
            label: "Gastos",
            data: daily.gastos,
            borderColor: colorGasto,
            backgroundColor: "rgba(239, 68, 68, 0.2)",
            tension: 0.3,
          },
        ],
      },
      options: {
        plugins: {
          legend: {
            labels: { color: "#e5f2ff", font: { size: 10 } },
          },
        },
        scales: {
          x: {
            ticks: { color: "#7f8ea3", font: { size: 9 } },
            grid: { display: false },
          },
          y: {
            ticks: { color: "#7f8ea3", font: { size: 9 } },
            grid: { color: "rgba(15,23,42,0.6)" },
          },
        },
      },
    });

    if (pieChartInstance) pieChartInstance.destroy();
    pieChartInstance = new window.Chart(pieCanvas.getContext("2d"), {
      type: "doughnut",
      data: {
        labels: cat.labels,
        datasets: [
          {
            data: cat.values,
            backgroundColor: [
              "#22e8c2",
              "#38bdf8",
              "#f97316",
              "#a855f7",
              "#facc15",
              "#10b981",
              "#ef4444",
            ],
          },
        ],
      },
      options: {
        plugins: {
          legend: {
            position: "bottom",
            labels: { color: "#e5f2ff", font: { size: 9 } },
          },
        },
      },
    });
  } catch {
    // sin gráficos si falla
  }
}

initCharts();

// Modal Editar etiquetas: reasignar conceptos a categorías analíticas
(function setupEditLabelsModal() {
  const btn = document.getElementById("btn-editar-etiquetas");
  const modal = document.getElementById("modal-etiquetas");
  const remapList = document.getElementById("remap-list");

  if (!btn || !modal || !remapList) return;

  function closeModal() {
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
  }

  modal.querySelectorAll("[data-close-modal]").forEach((el) => {
    el.addEventListener("click", closeModal);
  });

  btn.addEventListener("click", async () => {
    try {
      const res = await fetch("/api/analytics");
      if (!res.ok) return;
      const data = await res.json();

      const cat = data.categorias_gasto || { labels: [], values: [] };
      const analiticas = data.categorias_analiticas || [];

      const problematic = cat.labels.filter(
        (l) => l && !analiticas.includes(l)
      );

      if (problematic.length === 0) {
        remapList.innerHTML = '<p class="helper">Todas las etiquetas del gráfico ya son categorías analíticas correctas.</p>';
      } else {
        remapList.innerHTML = problematic
          .map(
            (label) => `
          <div class="remap-row" data-from="${label.replace(/"/g, "&quot;")}">
            <span class="remap-label">"${label.replace(/"/g, "&quot;")}"</span>
            <span>→</span>
            <select class="remap-to">
              ${analiticas.map((a) => `<option value="${a.replace(/"/g, "&quot;")}">${a}</option>`).join("")}
            </select>
            <button type="button" class="btn primary btn-sm remap-apply">Aplicar</button>
          </div>
        `
          )
          .join("");

        remapList.querySelectorAll(".remap-apply").forEach((applyBtn) => {
          applyBtn.addEventListener("click", async () => {
            const row = applyBtn.closest(".remap-row");
            const fromLabel = row.dataset.from;
            const toLabel = row.querySelector(".remap-to").value;
            if (!fromLabel || !toLabel) return;

            applyBtn.disabled = true;
            applyBtn.textContent = "…";

            try {
              const res = await fetch("/api/transactions/remap-category", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  from_label: fromLabel,
                  to_label: toLabel,
                }),
              });
              if (res.ok) {
                window.location.reload();
              } else {
                applyBtn.disabled = false;
                applyBtn.textContent = "Aplicar";
              }
            } catch {
              applyBtn.disabled = false;
              applyBtn.textContent = "Aplicar";
            }
          });
        });
      }

      modal.classList.remove("hidden");
      modal.setAttribute("aria-hidden", "false");
    } catch {
      // fallo al cargar
    }
  });
})();

// Gasto con subgastos (detalle de factura)
(function setupGastoDetalle() {
  const toggleBtn = document.getElementById("toggle-gasto-detalle");
  const panel = document.getElementById("gasto-detalle-panel");
  const tbody = document.getElementById("gasto-detalle-tbody");
  const addRowBtn = document.getElementById("add-detail-row");
  const totalEl = document.getElementById("gasto-detalle-total");
  const saveBtn = document.getElementById("save-gasto-detalle");
  const conceptInput = document.getElementById("gasto-detalle-concept");
  const dateInput = document.getElementById("gasto-detalle-date");
  const categorySelect = document.getElementById("gasto-detalle-category");

  if (!toggleBtn || !panel || !tbody || !saveBtn) return;

  toggleBtn.addEventListener("click", function () {
    const isHidden = panel.classList.contains("hidden");
    if (isHidden) {
      panel.classList.remove("hidden");
      toggleBtn.textContent = "− Ocultar gasto con subgastos";
      if (!dateInput.value) dateInput.value = new Date().toISOString().slice(0, 10);
    } else {
      panel.classList.add("hidden");
      toggleBtn.textContent = "+ Gasto con subgastos (detalle de factura)";
    }
  });

  function updateTotal() {
    let sum = 0;
    tbody.querySelectorAll(".detail-row").forEach(function (row) {
      const inp = row.querySelector(".detail-amount");
      if (inp && inp.value) sum += parseFloat(inp.value) || 0;
    });
    if (totalEl) totalEl.textContent = sum.toLocaleString("es-CO", { maximumFractionDigits: 0 });
  }

  function addDetailRow() {
    const row = document.createElement("tr");
    row.className = "detail-row";
    row.innerHTML =
      '<td><input type="text" class="detail-concept" placeholder="ej. peluche" /></td>' +
      '<td><input type="number" step="0.01" class="detail-amount" placeholder="0" /></td>' +
      '<td><button type="button" class="icon-btn remove-detail-row" title="Quitar" aria-label="Quitar ítem">×</button></td>';
    tbody.appendChild(row);
    row.querySelector(".detail-amount").addEventListener("input", updateTotal);
    row.querySelector(".remove-detail-row").addEventListener("click", function () {
      row.remove();
      updateTotal();
    });
    updateTotal();
  }

  if (addRowBtn) addRowBtn.addEventListener("click", addDetailRow);

  tbody.querySelectorAll(".detail-row").forEach(function (row) {
    row.querySelector(".detail-amount").addEventListener("input", updateTotal);
    var rm = row.querySelector(".remove-detail-row");
    if (rm) rm.addEventListener("click", function () { row.remove(); updateTotal(); });
  });
  updateTotal();

  saveBtn.addEventListener("click", async function () {
    const concept = (conceptInput && conceptInput.value || "").trim();
    const date = (dateInput && dateInput.value || "").trim();
    const category = (categorySelect && categorySelect.value) || "Otros";

    const lineItems = [];
    tbody.querySelectorAll(".detail-row").forEach(function (row) {
      const c = (row.querySelector(".detail-concept") || {}).value || "";
      const a = parseFloat((row.querySelector(".detail-amount") || {}).value) || 0;
      if (c.trim()) lineItems.push({ concept: c.trim(), amount: a });
    });

    if (!concept) {
      alert("Escribe el concepto del gasto (ej. Compra cosas de novia - Local MISUNO).");
      return;
    }
    if (lineItems.length === 0) {
      alert("Añade al menos un ítem (concepto y monto).");
      return;
    }

    saveBtn.disabled = true;
    saveBtn.textContent = "Guardando…";
    try {
      const res = await fetch("/add-expense-with-detail", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ concept: concept, date: date, category: category, line_items: lineItems }),
      });
      const data = await res.json().catch(function () { return {}; });
      if (data.ok) {
        window.location.reload();
      } else {
        alert("No se pudo guardar. Revisa los datos.");
      }
    } catch (e) {
      alert("Error de conexión.");
    }
    saveBtn.disabled = false;
    saveBtn.textContent = "Guardar gasto con detalle";
  });

  // Expandir / colapsar detalle de subgastos en la tabla de movimientos
  document.querySelectorAll(".btn-expand-detail").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var txId = btn.getAttribute("data-tx-id");
      var detailRow = document.querySelector('.detail-sub-row[data-detail-tx="' + txId + '"]');
      if (!detailRow) return;
      var isHidden = detailRow.classList.contains("hidden");
      detailRow.classList.toggle("hidden", !isHidden);
      btn.textContent = isHidden ? "▾" : "▸";
    });
  });
})();

// Agregar gastos con voz / IA (tabs: Voz, Pegar texto, Subir factura)
(function setupVoiceIA() {
  var btnOpen = document.getElementById("btn-voice-ia");
  var modal = document.getElementById("modal-voice-ia");
  var textarea = document.getElementById("voice-ia-text");
  var btnMic = document.getElementById("voice-ia-mic");
  var transcribingEl = document.getElementById("voice-ia-transcribing");
  var btnProcess = document.getElementById("voice-ia-process");
  var statusEl = document.getElementById("voice-ia-status");
  var fileInput = document.getElementById("voice-ia-file");
  var filenameEl = document.getElementById("voice-ia-filename");
  var panels = { voz: document.getElementById("voice-ia-panel-voz"), texto: document.getElementById("voice-ia-panel-texto"), factura: document.getElementById("voice-ia-panel-factura") };

  if (!btnOpen || !modal || !btnProcess) return;

  var chooser = modal.querySelector(".voice-ia-chooser");
  var chooseBtn = document.getElementById("voice-ia-choose-method");
  var popover = document.getElementById("voice-ia-popover");
  var changeMethodBtn = document.getElementById("voice-ia-change-method");
  var voiceBody = document.getElementById("voice-ia-body");

  function closeModal() {
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
    if (popover) popover.classList.add("hidden");
    if (chooser) chooser.classList.remove("open");
  }
  modal.querySelectorAll("[data-close-modal=\"voice\"]").forEach(function (el) {
    el.addEventListener("click", closeModal);
  });
  function openVoiceModal(initialTab) {
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    if (textarea) textarea.value = "";
    if (fileInput) fileInput.value = "";
    if (filenameEl) { filenameEl.classList.add("hidden"); filenameEl.textContent = ""; }
    if (statusEl) { statusEl.classList.add("hidden"); statusEl.textContent = ""; }
    if (transcribingEl) transcribingEl.classList.add("hidden");
    if (popover) popover.classList.add("hidden");
    if (chooser) chooser.classList.remove("open");
    if (voiceBody) voiceBody.classList.add("hidden");
    if (changeMethodBtn) changeMethodBtn.classList.add("hidden");
    if (chooseBtn) chooseBtn.classList.remove("hidden");
    document.querySelectorAll(".voice-ia-panel").forEach(function (p) { p.classList.add("hidden"); });
    if (initialTab && (initialTab === "voz" || initialTab === "texto" || initialTab === "factura")) {
      setTab(initialTab);
    }
  }
  window.openVoiceIAModal = openVoiceModal;
  btnOpen.addEventListener("click", function () { openVoiceModal(); });

  function setTab(id) {
    document.querySelectorAll(".voice-tab").forEach(function (t) { t.classList.remove("active"); });
    document.querySelectorAll(".voice-ia-panel").forEach(function (p) { p.classList.add("hidden"); });
    var t = document.querySelector('.voice-tab[data-tab="' + id + '"]');
    if (t) t.classList.add("active");
    if (panels[id]) panels[id].classList.remove("hidden");
    if (voiceBody) voiceBody.classList.remove("hidden");
    if (changeMethodBtn) changeMethodBtn.classList.remove("hidden");
    if (chooseBtn) chooseBtn.classList.add("hidden");
    if (popover) popover.classList.add("hidden");
    if (chooser) chooser.classList.remove("open");
  }
  document.querySelectorAll(".voice-tab").forEach(function (btn) {
    btn.addEventListener("click", function () { setTab(btn.getAttribute("data-tab")); });
  });
  if (chooseBtn && popover) {
    chooseBtn.addEventListener("click", function () {
      popover.classList.toggle("hidden");
      if (chooser) chooser.classList.toggle("open", !popover.classList.contains("hidden"));
    });
  }
  if (changeMethodBtn && popover && chooser) {
    changeMethodBtn.addEventListener("click", function () {
      popover.classList.remove("hidden");
      chooser.classList.add("open");
    });
  }
  modal.querySelectorAll(".voice-ia-option").forEach(function (btn) {
    btn.addEventListener("click", function () { setTab(btn.getAttribute("data-tab")); });
  });
  modal.addEventListener("click", function (e) {
    if (popover && !popover.classList.contains("hidden") && !popover.contains(e.target) && !chooseBtn.contains(e.target) && !(changeMethodBtn && changeMethodBtn.contains(e.target))) {
      popover.classList.add("hidden");
      if (chooser) chooser.classList.remove("open");
    }
  });

  var recognition = null;
  var isRecording = false;
  var lastProcessedIndex = -1;
  var transcriptFullEl = document.getElementById("voice-ia-transcript-full");
  var transcriptTextEl = document.getElementById("voice-ia-transcript-text");
  var lastInterim = "";

  function updateFullTranscript(interim) {
    if (interim !== undefined) lastInterim = interim;
    var full = (textarea ? textarea.value : "") + (lastInterim ? " " + lastInterim : "");
    full = full.trim();
    if (transcriptTextEl) transcriptTextEl.textContent = full;
    if (transcriptFullEl) {
      if (full) transcriptFullEl.classList.remove("hidden");
      else transcriptFullEl.classList.add("hidden");
    }
  }

  if (typeof window.SpeechRecognition !== "undefined" || typeof window.webkitSpeechRecognition !== "undefined") {
    var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SR();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "es-ES";
    recognition.maxAlternatives = 1;
    recognition.onresult = function (e) {
      var results = e.results;
      for (var i = 0; i < results.length; i++) {
        var result = results[i];
        var transcript = "";
        try {
          transcript = (result[0] && result[0].transcript) ? result[0].transcript : "";
        } catch (err) {}
        if (!transcript) continue;
        if (result.isFinal) {
          if (textarea) textarea.value = (textarea.value + " " + transcript).trim();
          lastProcessedIndex = i;
          lastInterim = "";
        } else {
          lastInterim = transcript;
        }
      }
      updateFullTranscript();
      if (transcribingEl) {
        if (transcriptTextEl && transcriptTextEl.textContent) transcribingEl.classList.add("hidden");
        else { transcribingEl.textContent = "Transcribiendo…"; transcribingEl.classList.remove("hidden"); }
      }
    };
    recognition.onend = function () {
      if (isRecording) {
        try { recognition.start(); } catch (err) {}
      } else {
        updateFullTranscript();
        if (transcribingEl && textarea && textarea.value) {
          transcribingEl.textContent = "Listo. Ya puedes procesar con IA.";
          transcribingEl.classList.remove("hidden");
        }
      }
    };
    recognition.onerror = function (e) {
      if (e.error === "no-speech" && textarea && textarea.value) return;
      if (transcribingEl) transcribingEl.textContent = "Error: " + (e.error || "desconocido");
    };
  }
  if (btnMic) {
    if (!recognition) btnMic.style.display = "none";
    else {
      btnMic.addEventListener("click", function () {
        if (isRecording) {
          isRecording = false;
          lastProcessedIndex = -1;
          recognition.stop();
          btnMic.classList.remove("recording");
          btnMic.querySelector(".mic-label").textContent = "Toca para grabar";
        updateFullTranscript();
        if (transcribingEl) {
          transcribingEl.textContent = textarea && textarea.value ? "Listo. Pulsa Procesar con IA." : "Sin audio detectado. Prueba de nuevo.";
          transcribingEl.classList.remove("hidden");
        }
        return;
        }
        isRecording = true;
        lastInterim = "";
        btnMic.classList.add("recording");
        btnMic.querySelector(".mic-label").textContent = "Toca para detener";
        if (textarea) textarea.value = "";
        if (transcriptFullEl) transcriptFullEl.classList.add("hidden");
        if (transcriptTextEl) transcriptTextEl.textContent = "";
        if (transcribingEl) { transcribingEl.textContent = "Transcribiendo…"; transcribingEl.classList.remove("hidden"); }
        try {
          recognition.start();
        } catch (err) {
          if (transcribingEl) transcribingEl.textContent = "Error al iniciar el micrófono. Comprueba los permisos.";
        }
      });
    }
  }

  if (fileInput && filenameEl) {
    fileInput.addEventListener("change", function () {
      if (fileInput.files.length) {
        filenameEl.textContent = fileInput.files[0].name;
        filenameEl.classList.remove("hidden");
      } else {
        filenameEl.classList.add("hidden");
      }
    });
  }

  // FIX: Unificar UI — enviar gastos de voz/IA por POST (sin quick-form legacy)
  function addItemsToTable(items) {
    if (!items || items.length === 0) return;
    var today = new Date().toISOString().slice(0, 10);
    var fd = new FormData();
    items.forEach(function (it) {
      fd.append("date_str", today);
      fd.append("amount", it.amount != null ? it.amount : 0);
      fd.append("type", "gasto");
      fd.append("category", "");
      fd.append("description", it.description || "");
    });
    closeModal();
    if (statusEl) { statusEl.textContent = "Guardando " + items.length + " movimiento(s)…"; statusEl.classList.remove("hidden"); }
    showLoading();
    fetch("/add-transaction", { method: "POST", body: fd })
      .then(function (r) {
        if (r.ok || r.redirected) window.location.reload();
        else if (statusEl) statusEl.textContent = "Error al guardar. Revisa e intenta de nuevo.";
      })
      .catch(function () {
        if (statusEl) statusEl.textContent = "Error de conexión. Intenta de nuevo.";
      })
      .then(function () { hideLoading(); });
  }

  btnProcess.addEventListener("click", async function () {
    var activeTab = document.querySelector(".voice-tab.active");
    var tab = activeTab ? activeTab.getAttribute("data-tab") : "voz";

    if (tab === "factura" && fileInput && fileInput.files.length > 0) {
      if (statusEl) { statusEl.textContent = "Procesando factura…"; statusEl.classList.remove("hidden"); }
      showLoading();
      try {
        var fd = new FormData();
        fd.append("file", fileInput.files[0]);
        var res = await fetch("/api/parse-expenses-from-image", { method: "POST", body: fd });
        var data = await res.json().catch(function () { return {}; });
        hideLoading();
        var items = data.items || [];
        if (items.length === 0) {
          if (statusEl) statusEl.textContent = "No se encontraron ítems en la factura.";
          return;
        }
        addItemsToTable(items);
      } catch (e) {
        hideLoading();
        if (statusEl) statusEl.textContent = "Error al procesar la imagen. Revisa la conexión o Gemini.";
      }
      return;
    }

    var text = (textarea && textarea.value || "").trim();
    if (!text) {
      if (statusEl) { statusEl.textContent = "Graba con el micrófono, pega texto o sube una factura."; statusEl.classList.remove("hidden"); }
      return;
    }
    if (statusEl) { statusEl.textContent = "Procesando con IA…"; statusEl.classList.remove("hidden"); }
    showLoading();
    try {
      var res = await fetch("/api/parse-expenses-from-text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text }),
      });
      var data = await res.json().catch(function () { return {}; });
      hideLoading();
      var items = data.items || [];
      if (items.length === 0) {
        if (statusEl) statusEl.textContent = "No se encontraron gastos. Prueba: pan 5000, café 3000.";
        return;
      }
      addItemsToTable(items);
    } catch (e) {
      hideLoading();
      if (statusEl) statusEl.textContent = "Error al procesar. Revisa la conexión o Gemini.";
    }
  });
})();

// Hints automáticos: la IA revisa todo y muestra consejos sin preguntar
(function loadHints() {
  const panel = document.getElementById("hints-panel");
  const list = document.getElementById("hints-list");
  if (!panel || !list) return;
  fetch("/api/advice/hints")
    .then((r) => r.ok ? r.json() : { hints: [] })
    .then((data) => {
      const hints = data.hints || [];
      if (hints.length === 0) return;
      list.innerHTML = hints.map((h) => `<li>${h}</li>`).join("");
      panel.classList.remove("hidden");
    })
    .catch(() => {});
})();

// Mission Control: score, runway, tasa ahorro, proyección fin de mes, semáforo
(function loadMissionControl() {
  const mc = document.getElementById("mission-control");
  const semaphorePanel = document.getElementById("semaphore-panel");
  const semaphoreTbody = document.getElementById("semaphore-tbody");
  if (!mc) return;

  function formatNum(n) {
    if (n == null || n === "") return "—";
    return new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 }).format(n);
  }

  function setFecha() {
    const el = document.getElementById("mc-fecha");
    if (el) el.textContent = new Date().toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  }

  Promise.all([
    fetch("/api/analytics/score").then((r) => (r.ok ? r.json() : {})),
    fetch("/api/analytics/month-projection").then((r) => (r.ok ? r.json() : {})),
    fetch("/api/analytics/category-semaphore").then((r) => (r.ok ? r.json() : {})),
    fetch("/api/advice/daily-briefing").then((r) => (r.ok ? r.json() : {})),
  ])
    .then(([scoreData, proyData, semData, briefingData]) => {
      setFecha();
      if (scoreData && scoreData.score != null) {
        const v = document.getElementById("mc-score-value");
        const f = document.getElementById("mc-score-fill");
        const vs = document.getElementById("mc-score-vs");
        if (v) v.textContent = scoreData.score + "/100";
        if (f) { f.style.width = scoreData.score + "%"; f.setAttribute("aria-valuenow", scoreData.score); }
        if (vs && scoreData.vs_mes_anterior != null) {
          const d = scoreData.vs_mes_anterior;
          vs.textContent = (d >= 0 ? "↑ +" : "↓ ") + d + " vs mes ant.";
        }
        const rw = document.getElementById("mc-runway");
        if (rw) rw.textContent = scoreData.runway_dias != null ? scoreData.runway_dias : "—";
        const ta = document.getElementById("mc-tasa");
        if (ta) ta.textContent = scoreData.tasa_ahorro != null ? scoreData.tasa_ahorro : "—";
      }
      if (proyData && proyData.proyeccion_fin_mes != null) {
        const t = document.getElementById("mc-proy-text");
        const rit = document.getElementById("mc-proy-ritmo");
        if (t) t.textContent = "Si sigues a este ritmo gastarás $" + formatNum(proyData.proyeccion_fin_mes) + " al cierre del mes.";
        if (rit) rit.textContent = "Ritmo: $" + formatNum(proyData.ritmo_diario) + "/día.";
      }
      if (briefingData && briefingData.bullets && briefingData.bullets.length > 0) {
        var list = document.getElementById("daily-briefing-list");
        if (list) list.innerHTML = briefingData.bullets.map(function (b) { return "<li>" + b + "</li>"; }).join("");
      }
      if (semData && semData.categorias && semData.categorias.length > 0 && semaphoreTbody) {
        const estadoIcon = { ok: "🟢", amarillo: "🟡", rojo: "🔴" };
        semaphoreTbody.innerHTML = semData.categorias
          .map(function (c) {
            return (
              "<tr><td>" +
              (c.category || "—") +
              "</td><td>$" +
              formatNum(c.mes_actual) +
              "</td><td>$" +
              formatNum(c.promedio) +
              "</td><td>" +
              (estadoIcon[c.estado] || "") +
              " " +
              (c.variacion_pct != null ? (c.variacion_pct >= 0 ? "+" : "") + c.variacion_pct + "%" : "") +
              "</td></tr>"
            );
          })
          .join("");
        if (semaphorePanel) semaphorePanel.classList.remove("hidden");
      }
      if (mc) mc.classList.remove("hidden");
      fetch("/api/notifications?unread_only=true")
        .then(function (r) { return r.ok ? r.json() : {}; })
        .then(function (d) {
          var n = d.unread_count || 0;
          var wrap = document.getElementById("notif-wrap");
          var badge = document.getElementById("notif-badge");
          var badgeLux = document.getElementById("notif-badge-lux");
          if (wrap && badge && n > 0) { badge.textContent = n; wrap.classList.remove("hidden"); }
          if (badgeLux) { badgeLux.textContent = n; if (n > 0) badgeLux.classList.remove("hidden"); else badgeLux.classList.add("hidden"); }
        })
        .catch(function () {});
    })
    .catch(function () {
      const t = document.getElementById("mc-proy-text");
      if (t) t.textContent = "No se pudo cargar la proyección.";
    });
})();

// CFO Personal: plan del mes + ideas de ingreso
(function setupCFOPanel() {
  const content = document.getElementById("cfo-plan-content");
  const subtitle = document.getElementById("cfo-subtitle");
  const btnRefresh = document.getElementById("btn-refresh-cfo");
  const btnChat = document.getElementById("btn-cfo-chat");
  const btnIncome = document.getElementById("btn-cfo-income-ideas");
  if (!content) return;

  window.loadCFOPlan = function () {
    if (subtitle) subtitle.textContent = "Revisando tu situación…";
    content.innerHTML = "<div class=\"loading-skeleton cfo-loading\">Analizando tu mes…</div>";
    fetch("/api/advice/cfo-plan")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (subtitle) subtitle.textContent = "Plan del mes";
        var html = data.plan || "No se pudo cargar el plan.";
        if (window.marked) html = window.marked.parse(html);
        content.innerHTML = html;
      })
      .catch(function () {
        if (subtitle) subtitle.textContent = "Error";
        content.innerHTML = "<p class=\"cfo-loading\">No se pudo conectar. Intenta de nuevo.</p>";
      });
  };

  window.loadIncomeIdeas = function () {
    if (subtitle) subtitle.textContent = "Generando ideas…";
    content.innerHTML = "<div class=\"loading-skeleton cfo-loading\">Buscando ideas de ingreso…</div>";
    fetch("/api/advice/income-ideas", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (subtitle) subtitle.textContent = "Ideas de ingreso";
        var html = data.ideas || "No se pudieron generar ideas.";
        if (window.marked) html = window.marked.parse(html);
        content.innerHTML = html;
      })
      .catch(function () {
        if (subtitle) subtitle.textContent = "Error";
        content.innerHTML = "<p class=\"cfo-loading\">No se pudo conectar. Intenta de nuevo.</p>";
      });
  };

  window.openCFOChat = function () {
    var drawer = document.getElementById("ia-drawer");
    var q = document.getElementById("question");
    if (drawer) drawer.classList.remove("hidden");
    if (q) q.focus();
  };

  if (btnRefresh) btnRefresh.addEventListener("click", window.loadCFOPlan);
  if (btnChat) btnChat.addEventListener("click", window.openCFOChat);
  if (btnIncome) btnIncome.addEventListener("click", window.loadIncomeIdeas);
  window.loadCFOPlan();
})();

// Badge de perfil incompleto (< 50%) en la nav
(function checkProfileBadge() {
  var badge = document.getElementById("perfil-badge");
  if (!badge) return;
  fetch("/api/profile/completeness")
    .then(function (r) { return r.ok ? r.json() : {}; })
    .then(function (d) {
      if (d.percent != null && d.percent < 50) badge.classList.remove("hidden");
      else badge.classList.add("hidden");
    })
    .catch(function () {});
})();

// ----- Vista Figma móvil: FAB +, sheet registro, drawer, filtros -----
(function setupFigmaMobile() {
  var overlay = document.getElementById("figma-registro-overlay");
  var form = document.getElementById("figma-registro-form");
  var fab = document.getElementById("figma-fab-add");
  var drawer = document.getElementById("figma-drawer");
  var drawerBackdrop = document.getElementById("figma-drawer-backdrop");
  var menuBtn = document.getElementById("figma-menu");
  var filterBtn = document.getElementById("figma-filter");
  var filterSheet = document.getElementById("figma-filter-sheet");
  var filterAplicar = document.getElementById("figma-filtro-aplicar");
  var movList = document.getElementById("figma-mov-list");

  var chooserStep = document.getElementById("lux-add-chooser");
  var formStep = document.getElementById("lux-add-form-step");
  var btnBack = document.getElementById("lux-add-back");
  var btnClose = document.getElementById("lux-add-close");
  var btnManual = document.getElementById("lux-add-manual");
  var btnVoice = document.getElementById("lux-add-voice");
  var btnImage = document.getElementById("lux-add-image");

  function showChooser() {
    if (chooserStep) chooserStep.classList.remove("hidden");
    if (formStep) formStep.classList.add("hidden");
  }
  function showForm() {
    if (chooserStep) chooserStep.classList.add("hidden");
    if (formStep) formStep.classList.remove("hidden");
  }

  function openRegistro() {
    if (overlay) {
      showChooser();
      overlay.classList.add("open");
      overlay.setAttribute("aria-hidden", "false");
      if (typeof lucide !== "undefined") lucide.createIcons();
    }
  }
  function closeRegistro() {
    if (overlay) {
      overlay.classList.remove("open");
      overlay.setAttribute("aria-hidden", "true");
      showChooser();
    }
  }
  if (fab) fab.addEventListener("click", openRegistro);
  var fabDesktop = document.getElementById("figma-fab-add-desktop");
  if (fabDesktop) fabDesktop.addEventListener("click", openRegistro);
  if (overlay) {
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) closeRegistro();
    });
  }
  if (btnClose) btnClose.addEventListener("click", closeRegistro);
  if (btnBack) btnBack.addEventListener("click", showChooser);
  if (btnManual) btnManual.addEventListener("click", function () { showForm(); });
  if (btnVoice) btnVoice.addEventListener("click", function () {
    closeRegistro();
    if (window.openVoiceIAModal) window.openVoiceIAModal("voz");
  });
  if (btnImage) btnImage.addEventListener("click", function () {
    closeRegistro();
    if (window.openVoiceIAModal) window.openVoiceIAModal("factura");
  });

  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var fd = new FormData(form);
      fetch("/add-transaction", { method: "POST", body: fd })
        .then(function (r) { if (r.ok) window.location.reload(); })
        .catch(function () {});
    });
  }

  if (menuBtn && drawer && drawerBackdrop) {
    function openDrawer() { drawer.classList.add("open"); drawer.setAttribute("aria-hidden", "false"); }
    function closeDrawer() { drawer.classList.remove("open"); drawer.setAttribute("aria-hidden", "true"); }
    menuBtn.addEventListener("click", openDrawer);
    drawerBackdrop.addEventListener("click", closeDrawer);
  }

  if (filterBtn && filterSheet) {
    filterBtn.addEventListener("click", function () {
      filterSheet.classList.add("open");
      filterSheet.setAttribute("aria-hidden", "false");
    });
    filterSheet.addEventListener("click", function (e) {
      if (e.target === filterSheet) {
        filterSheet.classList.remove("open");
        filterSheet.setAttribute("aria-hidden", "true");
      }
    });
  }
  if (filterAplicar && filterSheet && movList) {
    var catSelect = document.getElementById("figma-filtro-categoria");
    var tipoSelect = document.getElementById("figma-filtro-tipo");
    filterAplicar.addEventListener("click", function () {
      var cat = (catSelect && catSelect.value) || "";
      var tipo = (tipoSelect && tipoSelect.value) || "";
      var items = movList.querySelectorAll(".figma-mov-item");
      items.forEach(function (li) {
        var rowCat = (li.dataset.txCategory || "").trim();
        var rowTipo = (li.dataset.txType || "").trim();
        var show = (!cat || rowCat === cat) && (!tipo || rowTipo === tipo);
        li.style.display = show ? "" : "none";
      });
      filterSheet.classList.remove("open");
      filterSheet.setAttribute("aria-hidden", "true");
    });
  }
})();
