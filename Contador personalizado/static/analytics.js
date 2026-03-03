(function () {
  function formatNum(n) {
    if (n == null || n === "") return "—";
    return new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 }).format(n);
  }

  var chartMonthly = null;
  var chartWeekly = null;

  function renderMonthly(data) {
    if (!data || !data.labels || data.labels.length === 0) {
      document.getElementById("chart-monthly").parentElement.innerHTML = "<p class='helper'>No hay datos. Genera snapshots del mes anterior desde el backend.</p>";
      return;
    }
    var ctx = document.getElementById("chart-monthly");
    if (!ctx) return;
    if (chartMonthly) chartMonthly.destroy();
    chartMonthly = new Chart(ctx, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [
          { label: "Ingresos", data: data.ingresos, backgroundColor: "rgba(34, 197, 94, 0.6)" },
          { label: "Gastos", data: data.gastos, backgroundColor: "rgba(239, 68, 68, 0.6)" },
        ],
      },
      options: {
        responsive: true,
        plugins: { legend: { position: "top" } },
        scales: { y: { beginAtZero: true } },
      },
    });
  }

  function renderWeekly(data) {
    var ctx = document.getElementById("chart-weekly");
    if (!ctx) return;
    var labels = data.labels || ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
    var values = labels.map(function (_, i) { return data.por_dia && data.por_dia[i] != null ? data.por_dia[i] : 0; });
    if (chartWeekly) chartWeekly.destroy();
    chartWeekly = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [{ label: "Gastos (COP)", data: values, backgroundColor: "rgba(56, 189, 248, 0.6)" }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true } },
      },
    });
  }

  function renderTopExpenses(items) {
    var tbody = document.getElementById("top-expenses-tbody");
    if (!tbody) return;
    if (!items || items.length === 0) {
      tbody.innerHTML = "<tr><td colspan='4'>No hay gastos este mes.</td></tr>";
      return;
    }
    tbody.innerHTML = items
      .map(function (it) {
        return (
          "<tr><td>" +
          (it.date || "—") +
          "</td><td>" +
          (it.concept || "—") +
          "</td><td>" +
          (it.category || "—") +
          "</td><td>$" +
          formatNum(it.amount) +
          "</td></tr>"
        );
      })
      .join("");
  }

  function renderProjection(data) {
    var box = document.getElementById("projection-box");
    if (!box) return;
    if (!data || data.proyeccion_fin_mes == null) {
      box.innerHTML = "<p class='helper'>No hay datos suficientes.</p>";
      return;
    }
    box.innerHTML =
      "<p><strong>Gastos proyectados a fin de mes:</strong> $" +
      formatNum(data.proyeccion_fin_mes) +
      "</p>" +
      "<p>Ritmo diario: $" +
      formatNum(data.ritmo_diario) +
      "/día. Disponible proyectado: $" +
      formatNum(data.disponible_proyectado) +
      "</p>";
  }

  Promise.all([
    fetch("/api/analytics/monthly-evolution").then(function (r) { return r.ok ? r.json() : {}; }),
    fetch("/api/analytics/weekly-pattern").then(function (r) { return r.ok ? r.json() : {}; }),
    fetch("/api/analytics/top-expenses").then(function (r) { return r.ok ? r.json() : {}; }),
    fetch("/api/analytics/month-projection").then(function (r) { return r.ok ? r.json() : {}; }),
  ]).then(function (results) {
    renderMonthly(results[0]);
    renderWeekly(results[1]);
    renderTopExpenses((results[2] && results[2].items) || []);
    renderProjection(results[3]);
  });
})();
