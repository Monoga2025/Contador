(function () {
  "use strict";

  var STORAGE_PREFIX = "lux_tour_";
  var stepsByPage = {
    index: [
      { target: "#tour-inicio-resumen", title: "Tu resumen", text: "Aquí ves tu puntuación y el dinero disponible este mes (ingresos y gastos)." },
      { target: "#figma-fab-add-desktop", title: "Registrar movimiento", text: "Toca aquí para agregar un gasto o ingreso con voz, texto o subiendo una factura (la IA lo procesa)." },
      { target: "#tour-inicio-cfo", title: "Asesor CFO", text: "Tu asesor IA te da el plan del mes y puedes preguntarle lo que quieras sobre tus finanzas." },
      { target: "#tour-inicio-nav", title: "Navegación", text: "Inicio, Analítica, Objetivos, Perfil y Config. En Objetivos defines tus metas de ahorro." }
    ],
    objetivos: [
      { target: "#tour-objetivos-resumen", title: "Resumen del mes", text: "Ingresos, gastos y disponible. Sirve de contexto para tus metas." },
      { target: "#tour-objetivos-ahorro", title: "Ahorro actual", text: "Indica cuánto tienes ahorrado; la IA lo usa para recomendaciones y proyecciones." },
      { target: "#tour-objetivos-agregar", title: "Agregar objetivo", text: "Crea una meta: nombre, monto a alcanzar, frecuencia y fecha límite opcional." },
      { target: "#tour-objetivos-calendario", title: "Calendario de metas", text: "Los días con fecha límite de un objetivo se marcan como meta. Así ves cuándo vencen." },
      { target: "#tour-objetivos-lista", title: "Mis objetivos", text: "Lista de metas con progreso, cuánto falta y estrategia IA por objetivo." },
      { target: "#tour-objetivos-asesor", title: "Asesor IA", text: "Pregunta cuánto ahorrar o en cuánto tiempo puedes cumplir tus objetivos." }
    ]
  };

  function getPageName() {
    var body = document.body;
    if (body.classList.contains("lux-home")) return "index";
    if (body.classList.contains("lux-objetivos")) return "objetivos";
    return "index";
  }

  function storageKey(page) {
    return STORAGE_PREFIX + page + "_done";
  }

  function wasTourDone(page) {
    try {
      return localStorage.getItem(storageKey(page)) === "1";
    } catch (e) {
      return false;
    }
  }

  function setTourDone(page) {
    try {
      localStorage.setItem(storageKey(page), "1");
    } catch (e) {}
  }

  function createOverlay() {
    var overlay = document.getElementById("lux-tour-overlay");
    if (overlay) return overlay;
    overlay = document.createElement("div");
    overlay.id = "lux-tour-overlay";
    overlay.className = "lux-tour-overlay";
    overlay.setAttribute("aria-hidden", "true");
    document.body.appendChild(overlay);
    return overlay;
  }

  function createSpotlight() {
    var el = document.getElementById("lux-tour-spotlight");
    if (el) return el;
    el = document.createElement("div");
    el.id = "lux-tour-spotlight";
    el.className = "lux-tour-spotlight";
    document.body.appendChild(el);
    return el;
  }

  function createCard() {
    var card = document.getElementById("lux-tour-card");
    if (card) return card;
    card = document.createElement("div");
    card.id = "lux-tour-card";
    card.className = "lux-tour-card";
    card.innerHTML =
      '<p class="lux-tour-progress" id="lux-tour-progress"></p>' +
      '<h4 id="lux-tour-title"></h4>' +
      '<p id="lux-tour-text"></p>' +
      '<div class="lux-tour-actions">' +
      '<button type="button" class="lux-tour-skip" id="lux-tour-skip">Omitir</button>' +
      '<button type="button" class="lux-tour-next" id="lux-tour-next">Siguiente</button>' +
      "</div>";
    document.body.appendChild(card);
    return card;
  }

  function positionSpotlight(rect, padding) {
    var spot = document.getElementById("lux-tour-spotlight");
    if (!spot) return;
    padding = padding || 8;
    spot.style.top = (rect.top - padding) + "px";
    spot.style.left = (rect.left - padding) + "px";
    spot.style.width = (rect.width + padding * 2) + "px";
    spot.style.height = (rect.height + padding * 2) + "px";
  }

  function positionCard(rect, stepIndex, total) {
    var card = document.getElementById("lux-tour-card");
    if (!card) return;
    var progress = document.getElementById("lux-tour-progress");
    var title = document.getElementById("lux-tour-title");
    var text = document.getElementById("lux-tour-text");
    var nextBtn = document.getElementById("lux-tour-next");

    if (progress) progress.textContent = (stepIndex + 1) + " / " + total;
    if (title) title.textContent = card.dataset.title || "";
    if (text) text.textContent = card.dataset.text || "";
    if (nextBtn) nextBtn.textContent = stepIndex === total - 1 ? "Listo" : "Siguiente";

    var cardRect = card.getBoundingClientRect();
    var gap = 16;
    var preferBottom = rect.bottom + gap + cardRect.height <= window.innerHeight;
    var x = rect.left;
    var y = preferBottom ? rect.bottom + gap : rect.top - cardRect.height - gap;
    if (x + cardRect.width > window.innerWidth - 20) x = window.innerWidth - cardRect.width - 20;
    if (x < 20) x = 20;
    if (y < 20) y = 20;
    if (y + cardRect.height > window.innerHeight - 20) y = window.innerHeight - cardRect.height - 20;
    card.style.left = x + "px";
    card.style.top = y + "px";
  }

  function showStep(page, index, autoStart) {
    var steps = stepsByPage[page];
    if (!steps || index >= steps.length) {
      endTour(page);
      return;
    }
    var step = steps[index];
    var target = document.querySelector(step.target);
    var overlay = createOverlay();
    var spotlight = createSpotlight();
    var card = createCard();

    overlay.classList.add("is-active");
    overlay.setAttribute("aria-hidden", "false");

    if (target) {
      var rect = target.getBoundingClientRect();
      positionSpotlight(rect);
      card.dataset.title = step.title;
      card.dataset.text = step.text;
      positionCard(rect, index, steps.length);
    } else {
      spotlight.style.display = "none";
      card.dataset.title = step.title;
      card.dataset.text = step.text;
      card.style.left = "50%";
      card.style.top = "50%";
      card.style.transform = "translate(-50%, -50%)";
      positionCard({ left: window.innerWidth / 2 - 160, top: window.innerHeight / 2 - 80, width: 320, height: 160 }, index, steps.length);
    }

    card.classList.remove("is-hidden");

    function goNext() {
      card.classList.add("is-hidden");
      showStep(page, index + 1, false);
    }

    function skip() {
      endTour(page);
    }

    var nextBtn = document.getElementById("lux-tour-next");
    var skipBtn = document.getElementById("lux-tour-skip");
    if (nextBtn) {
      nextBtn.onclick = function () {
        if (index === steps.length - 1) endTour(page);
        else goNext();
      };
    }
    if (skipBtn) skipBtn.onclick = skip;
    overlay.onclick = skip;
  }

  function endTour(page) {
    var overlay = document.getElementById("lux-tour-overlay");
    var spotlight = document.getElementById("lux-tour-spotlight");
    var card = document.getElementById("lux-tour-card");
    if (overlay) {
      overlay.classList.remove("is-active");
      overlay.setAttribute("aria-hidden", "true");
    }
    if (spotlight) spotlight.style.display = "none";
    if (card) card.classList.add("is-hidden");
    if (page) setTourDone(page);
  }

  function startTour(force) {
    var page = getPageName();
    var steps = stepsByPage[page];
    if (!steps || steps.length === 0) return;
    if (!force && wasTourDone(page)) return;
    showStep(page, 0, true);
  }

  function init() {
    var btn = document.getElementById("lux-tour-start");
    if (btn) btn.addEventListener("click", function () { startTour(true); });

    var page = getPageName();
    if (page === "index" && !wasTourDone("index")) {
      var onboarding = document.getElementById("onboarding-modal");
      if (onboarding && !onboarding.classList.contains("hidden")) {
        var closeBtn = onboarding.querySelector("[data-close-onboarding]");
        if (closeBtn) {
          closeBtn.addEventListener("click", function once() {
            closeBtn.removeEventListener("click", once);
            setTimeout(function () { startTour(false); }, 400);
          });
        }
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.LuxTour = { start: startTour, end: endTour };
})();
