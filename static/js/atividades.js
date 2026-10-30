(function () {
  function csrf() {
    var match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    if (match) return decodeURIComponent(match[1]);
    var input = document.querySelector("input[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function fmt(sec) {
    sec = Math.max(0, Math.floor(sec || 0));
    var h = Math.floor(sec / 3600);
    var m = Math.floor((sec % 3600) / 60);
    var s = sec % 60;
    var pad = function (n) { return (n < 10 ? "0" : "") + n; };
    return h + ":" + pad(m) + ":" + pad(s);
  }

  function toast(texto, acao) {
    var antigo = document.querySelector(".sgi-toast.js-live");
    if (antigo) antigo.remove();
    var box = document.createElement("div");
    box.className = "sgi-toast js-live";
    box.setAttribute("role", "status");
    var span = document.createElement("span");
    span.textContent = texto;
    box.appendChild(span);
    if (acao && acao.label && acao.onClick) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = acao.label;
      btn.addEventListener("click", function () {
        acao.onClick();
        box.remove();
      });
      box.appendChild(btn);
    }
    document.body.appendChild(box);
    setTimeout(function () {
      if (box.parentNode) box.remove();
    }, 4200);
  }

  function post(url, fields) {
    var body = new FormData();
    var token = csrf();
    if (token) body.append("csrfmiddlewaretoken", token);
    Object.keys(fields || {}).forEach(function (key) {
      var value = fields[key];
      if (value === undefined || value === null) return;
      body.append(key, value);
    });
    return fetch(url, {
      method: "POST",
      body: body,
      credentials: "same-origin",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
      },
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok || data.ok === false) {
          var erro = new Error(data.erro || "Não foi possível salvar.");
          erro.status = response.status;
          throw erro;
        }
        return data;
      });
    });
  }

  function pintarTimer(btn, data) {
    if (!btn || !data) return;
    btn.classList.toggle("is-running", !!data.ativo || !!data.cronometro_ativo);
    var ativo = !!(data.ativo || data.cronometro_ativo);
    var icon = btn.querySelector(".cu-timer-icon");
    var text = btn.querySelector(".cu-timer-text");
    if (icon) icon.textContent = ativo ? "❚❚" : "▶";
    if (text) text.textContent = data.texto || fmt(data.segundos || 0);
    btn.setAttribute("data-segundos", String(data.segundos || 0));
    btn.setAttribute("data-acumulado", String(data.acumulado || 0));
    btn.setAttribute("data-inicio", data.inicio || "");
    btn.title = ativo ? "Pausar" : "Iniciar";
  }

  document.querySelectorAll(".cu-status-form").forEach(function (form) {
    var sel = form.querySelector("select[name=status]");
    if (!sel || sel.dataset.bound) return;
    sel.dataset.bound = "1";
    sel.dataset.prev = sel.value;
    sel.addEventListener("change", function () {
      var anterior = sel.dataset.prev || sel.value;
      var destino = sel.value;
      post(form.action, { status: destino }).then(function (data) {
        sel.dataset.prev = data.status || destino;
        sel.className = sel.className.replace(/status-[\w]+/g, "").trim();
        sel.classList.add("cu-status-select", "status-" + (data.status || destino));
        var row = form.closest(".cu-row");
        if (row) row.classList.toggle("is-done", (data.status || destino) === "realizado");
        var timerBtn = row ? row.querySelector(".cu-timer-btn") : null;
        if (timerBtn && data.texto) pintarTimer(timerBtn, data);
        var label = sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].text : destino;
        if ((data.status || destino) === "executando" && !data.cronometro_ativo) {
          toast("Movida para " + label, {
            label: "Iniciar timer",
            onClick: function () {
              var timerForm = row ? row.querySelector(".cu-timer-form") : null;
              if (!timerForm) return;
              post(timerForm.action, {}).then(function (timer) {
                pintarTimer(timerBtn, timer);
                toast("Timer iniciado");
              }).catch(function (err) { toast(err.message); });
            },
          });
          return;
        }
        toast("Movida para " + label);
      }).catch(function (err) {
        sel.value = anterior;
        toast(err.message || "Não foi possível mudar o status.");
      });
    });
  });

  document.querySelectorAll(".cu-timer-form").forEach(function (form) {
    if (form.dataset.bound) return;
    form.dataset.bound = "1";
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var btn = form.querySelector(".cu-timer-btn");
      post(form.action, {}).then(function (data) {
        pintarTimer(btn, data);
      }).catch(function (err) {
        toast(err.message || "Não foi possível usar o timer.");
      });
    });
  });

  document.querySelectorAll("form.js-async").forEach(function (form) {
    if (form.dataset.bound) return;
    form.dataset.bound = "1";
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var fields = {};
      new FormData(form).forEach(function (value, key) {
        if (key !== "csrfmiddlewaretoken") fields[key] = value;
      });
      post(form.action, fields).then(function (data) {
        var btn = form.querySelector("button");
        if (form.classList.contains("pp-drop-form") && btn) {
          var cheio = document.querySelectorAll(".pp-drop.is-full").length;
          document.querySelectorAll(".pp-drop").forEach(function (drop, index) {
            drop.classList.toggle("is-full", index < (data.copos || 0));
            drop.setAttribute("aria-pressed", index < (data.copos || 0) ? "true" : "false");
          });
          var meta = document.querySelector(".pp-water-scale");
          if (meta) meta.style.setProperty("--agua-done", String(data.copos || 0));
          return;
        }
        if (btn && btn.classList.contains("pp-habit-cell")) {
          btn.classList.toggle("is-on", !!data.feito);
          btn.textContent = data.feito ? "✓" : "";
          return;
        }
        if (btn && btn.classList.contains("pp-check-btn")) {
          btn.textContent = data.concluida ? "✓" : "";
          var li = form.closest("li");
          if (li) li.classList.toggle("is-done", !!data.concluida);
          return;
        }
        if (btn && btn.classList.contains("eisen-badge") && data.quadrante) {
          btn.className = "eisen-badge q-" + data.quadrante;
          btn.textContent = data.sigla || btn.textContent;
          btn.title = data.label || btn.title;
          return;
        }
        if (btn && btn.classList.contains("pp-goal-num")) {
          var liMeta = form.closest("li");
          if (liMeta) liMeta.classList.toggle("is-done", !!data.concluida);
          btn.textContent = data.concluida ? "✓" : btn.textContent;
          return;
        }
        if (form.classList.contains("pp-inline-add") && data.texto) {
          var lista = document.querySelector(".pp-goals");
          if (lista) {
            var vazio = lista.querySelector(".muted");
            if (vazio) vazio.remove();
            var liNova = document.createElement("li");
            liNova.innerHTML = "<span class='pp-goal-num'>" + String(lista.children.length + 1).padStart(2, "0") + "</span><span></span>";
            liNova.querySelector("span:last-child").textContent = data.texto;
            lista.appendChild(liNova);
          }
          var input = form.querySelector("input[name=texto], input[name=titulo]");
          if (input) input.value = "";
          toast("Adicionado");
        }
      }).catch(function (err) {
        toast(err.message || "Não foi possível salvar.");
      });
    });
  });

  window.SGIAtividades = { post: post, fmt: fmt, toast: toast, pintarTimer: pintarTimer };
})();
