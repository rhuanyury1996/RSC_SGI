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

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form || !form.classList || !form.classList.contains("cu-timer-form") || form.dataset.bound) return;
    event.preventDefault();
    var btn = form.querySelector(".cu-timer-btn");
    post(form.action, {}).then(function (data) {
      pintarTimer(btn, data);
    }).catch(function (err) { toast(err.message || "Não foi possível usar o timer."); });
  }, true);

  window.SGIAtividades = { post: post, fmt: fmt, toast: toast, pintarTimer: pintarTimer };

  document.querySelectorAll(".kb-avatar").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var params = new URLSearchParams(location.search);
      var ids = (params.get("pessoas") || "").split(",").filter(Boolean);
      var id = btn.getAttribute("data-id");
      var idx = ids.indexOf(id);
      if (idx >= 0) ids.splice(idx, 1);
      else ids.push(id);
      if (ids.length) params.set("pessoas", ids.join(","));
      else params.delete("pessoas");
      params.delete("minhas");
      params.delete("escopo");
      location.search = params.toString();
    });
  });

  document.querySelectorAll(".kb-lane-add").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var lane = btn.closest(".kb-lane");
      var cols = lane ? lane.querySelector(".kb-columns") : null;
      if (!cols) return;
      cols.hidden = false;
      lane.classList.remove("is-empty");
      var input = cols.querySelector(".kb-quick-input");
      if (input) input.focus();
    });
  });

  function moverCard(card, status, listaOrigem) {
    var lista = document.querySelector('.kb-list[data-status="' + status + '"]');
    var lane = card.closest(".kb-lane");
    if (lane) {
      lista = lane.querySelector('.kb-list[data-status="' + status + '"]') || lista;
    }
    if (!lista) return;
    lista.appendChild(card);
    card.setAttribute("data-status", status);
    post("/atividades/" + card.getAttribute("data-id") + "/status/", { status: status })
      .then(function (data) {
        var label = data.label || status;
        if (status === "executando" && !data.cronometro_ativo) {
          toast("Movida para " + label, {
            label: "Iniciar timer",
            onClick: function () {
              post(card.getAttribute("data-timer-url"), {}).then(function (timer) {
                pintarTimer(card.querySelector(".cu-timer-btn"), timer);
                toast("Timer iniciado");
              }).catch(function (err) { toast(err.message); });
            },
          });
        } else {
          toast("Movida para " + label);
        }
        document.querySelectorAll(".kb-col").forEach(function (col) {
          var n = col.querySelectorAll(".kb-card").length;
          var badge = col.querySelector("[data-count]");
          if (badge) badge.textContent = String(n);
        });
      })
      .catch(function (err) {
        if (listaOrigem) listaOrigem.appendChild(card);
        toast(err.message || "Não foi possível mover a tarefa.");
      });
  }

  var board = document.getElementById("kanban");
  if (board) {
    board.querySelectorAll(".kb-card").forEach(function (card) {
      card.addEventListener("dragstart", function (event) {
        event.dataTransfer.setData("text/plain", card.getAttribute("data-id"));
        card.classList.add("is-dragging");
      });
      card.addEventListener("dragend", function () { card.classList.remove("is-dragging"); });
      card.addEventListener("keydown", function (event) {
        var cards = Array.prototype.slice.call(board.querySelectorAll(".kb-card"));
        var idx = cards.indexOf(card);
        if (event.key === "ArrowRight" || event.key === "ArrowDown") {
          if (cards[idx + 1]) { cards[idx + 1].focus(); event.preventDefault(); }
        } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
          if (cards[idx - 1]) { cards[idx - 1].focus(); event.preventDefault(); }
        }
      });
    });
    board.querySelectorAll(".kb-list").forEach(function (lista) {
      lista.addEventListener("dragover", function (event) { event.preventDefault(); });
      lista.addEventListener("drop", function (event) {
        event.preventDefault();
        var id = event.dataTransfer.getData("text/plain");
        var card = board.querySelector('.kb-card[data-id="' + id + '"]');
        if (!card) return;
        var origem = card.parentElement;
        var status = lista.getAttribute("data-status");
        if (card.getAttribute("data-status") === status) return;
        moverCard(card, status, origem);
      });
    });
    board.querySelectorAll("[data-move]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var card = btn.closest(".kb-card");
        if (!card) return;
        moverCard(card, btn.getAttribute("data-move"), card.parentElement);
        var menu = btn.closest("details");
        if (menu) menu.open = false;
      });
    });
    board.querySelectorAll(".kb-quick").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        var input = form.querySelector("[name=titulo]");
        if (!input || !input.value.trim()) return;
        var fields = {};
        new FormData(form).forEach(function (value, key) {
          if (key !== "csrfmiddlewaretoken") fields[key] = value;
        });
        post(form.action, fields).then(function (data) {
          var lista = form.parentElement.querySelector(".kb-list");
          if (lista && data.html) {
            var holder = document.createElement("div");
            holder.innerHTML = data.html;
            var card = holder.firstElementChild;
            if (card) lista.prepend(card);
          }
          input.value = "";
          toast(data.aviso ? "Tarefa adicionada. " + data.aviso : "Tarefa adicionada");
        }).catch(function (err) { toast(err.message); });
      });
    });
  }

  var drawer = document.getElementById("kbDrawer");
  var backdrop = document.getElementById("kbBackdrop");
  var drawerForm = document.getElementById("kbDrawerForm");
  function fecharDrawer() {
    if (drawer) drawer.hidden = true;
    if (backdrop) backdrop.hidden = true;
  }
  function abrirDrawer(card) {
    if (!drawer || !drawerForm || !card) return;
    drawerForm.action = card.getAttribute("data-edit-url") || "";
    drawerForm.dataset.comment = card.getAttribute("data-comment-url") || "";
    drawerForm.dataset.del = card.getAttribute("data-delete-url") || "";
    var titulo = document.getElementById("kbDrawerTitle");
    if (titulo) titulo.textContent = card.getAttribute("data-titulo") || "Tarefa";
    var map = {
      kbTitulo: "data-titulo",
      kbStatus: "data-status",
      kbPrioridade: "data-prioridade",
      kbResponsavel: "data-responsavel",
      kbEmpresa: "data-cliente",
      kbData: "data-planejado",
      kbInicio: "data-hora-inicio",
      kbFim: "data-hora-fim",
      kbVenc: "data-vencimento",
      kbQuadrante: "data-quadrante",
      kbDescricao: "data-descricao",
    };
    Object.keys(map).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.value = card.getAttribute(map[id]) || "";
    });
    var parts = (card.getAttribute("data-participantes") || "").split(",").filter(Boolean);
    var resp = card.getAttribute("data-responsavel") || "";
    drawerForm.querySelectorAll("input[name=participantes]").forEach(function (chk) {
      chk.checked = parts.indexOf(chk.value) !== -1 && chk.value !== resp;
      var chip = chk.closest("label");
      if (chip) chip.style.display = chk.value === resp ? "none" : "";
    });
    var pode = card.getAttribute("data-pode-editar") === "1";
    drawerForm.querySelectorAll("input, select, textarea").forEach(function (el) {
      if (el.id === "kbComentario") return;
      el.disabled = !pode && el.type !== "hidden";
    });
    var salvar = document.getElementById("kbSalvar");
    var excluir = document.getElementById("kbExcluir");
    if (salvar) salvar.hidden = !pode;
    if (excluir) excluir.hidden = !pode;
    drawer.hidden = false;
    backdrop.hidden = false;
    fetch(card.getAttribute("data-detail-url"), { headers: { "Accept": "application/json" }, credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var hist = document.getElementById("kbHistorico");
        var subs = document.getElementById("kbSubs");
        if (hist) {
          hist.innerHTML = "";
          (data.eventos || []).forEach(function (ev) {
            var li = document.createElement("li");
            li.textContent = ev.quando + " · " + ev.autor + " · " + (ev.texto || ev.tipo_label);
            hist.appendChild(li);
          });
          if (!hist.children.length) hist.innerHTML = "<li class='muted'>Sem registros ainda.</li>";
        }
        if (subs) {
          subs.innerHTML = "";
          (data.subtarefas || []).forEach(function (sub) {
            var li = document.createElement("li");
            var box = document.createElement("input");
            box.type = "checkbox";
            box.checked = sub.status === "realizado";
            box.disabled = !sub.pode_marcar;
            box.addEventListener("change", function () {
              post("/atividades/" + sub.id + "/status/", {
                status: box.checked ? "realizado" : "nao_iniciado",
              }).catch(function (err) {
                box.checked = !box.checked;
                toast(err.message);
              });
            });
            li.appendChild(box);
            li.appendChild(document.createTextNode(" " + sub.titulo + (sub.responsavel ? " · " + sub.responsavel : "")));
            subs.appendChild(li);
          });
        }
      })
      .catch(function () { toast("Não foi possível carregar o histórico."); });
  }
  if (board) {
    board.addEventListener("dragstart", function (event) {
      var card = event.target.closest(".kb-card");
      if (!card) return;
      event.dataTransfer.setData("text/plain", card.getAttribute("data-id"));
      card.classList.add("is-dragging");
    });
    board.addEventListener("click", function (event) {
      var move = event.target.closest("[data-move]");
      if (move) {
        var cardMove = move.closest(".kb-card");
        if (!cardMove) return;
        moverCard(cardMove, move.getAttribute("data-move"), cardMove.parentElement);
        var menu = move.closest("details");
        if (menu) menu.open = false;
        return;
      }
      var open = event.target.closest(".kb-open");
      if (!open) return;
      abrirDrawer(open.closest(".kb-card"));
    });
  }
  var fechar = document.getElementById("kbDrawerClose");
  if (fechar) fechar.addEventListener("click", fecharDrawer);
  if (backdrop) backdrop.addEventListener("click", fecharDrawer);
  var respSel = document.getElementById("kbResponsavel");
  if (respSel) {
    respSel.addEventListener("change", function () {
      var resp = respSel.value;
      drawerForm.querySelectorAll("input[name=participantes]").forEach(function (chk) {
        var chip = chk.closest("label");
        var hide = chk.value === resp;
        if (chip) chip.style.display = hide ? "none" : "";
        if (hide) chk.checked = false;
      });
    });
  }
  if (drawerForm) {
    drawerForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var fields = {};
      new FormData(drawerForm).forEach(function (value, key) {
        if (key === "participantes") return;
        if (key !== "csrfmiddlewaretoken") fields[key] = value;
      });
      var partes = [];
      drawerForm.querySelectorAll("input[name=participantes]:checked").forEach(function (chk) {
        partes.push(chk.value);
      });
      var body = new FormData();
      var token = csrf();
      if (token) body.append("csrfmiddlewaretoken", token);
      Object.keys(fields).forEach(function (key) { body.append(key, fields[key]); });
      partes.forEach(function (id) { body.append("participantes", id); });
      fetch(drawerForm.action, {
        method: "POST",
        body: body,
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest", "Accept": "application/json" },
      }).then(function (r) { return r.json().then(function (data) { data._ok = r.ok; return data; }); })
        .then(function (data) {
          if (!data._ok || data.ok === false) throw new Error(data.erro || "Não foi possível salvar.");
          toast(data.aviso ? "Tarefa atualizada. " + data.aviso : "Tarefa atualizada");
          fecharDrawer();
          location.reload();
        })
        .catch(function (err) { toast(err.message); });
    });
  }
  var btnComment = document.getElementById("kbComentar");
  if (btnComment) {
    btnComment.addEventListener("click", function () {
      var texto = (document.getElementById("kbComentario") || {}).value || "";
      texto = texto.trim();
      if (!texto || !drawerForm.dataset.comment) return;
      post(drawerForm.dataset.comment, { texto: texto }).then(function (data) {
        var hist = document.getElementById("kbHistorico");
        if (hist) {
          var li = document.createElement("li");
          li.textContent = (data.quando || "") + " · " + (data.autor || "") + " · " + data.texto;
          hist.appendChild(li);
        }
        document.getElementById("kbComentario").value = "";
        toast("Comentário registrado");
      }).catch(function (err) { toast(err.message); });
    });
  }
  var btnDel = document.getElementById("kbExcluir");
  if (btnDel) {
    btnDel.addEventListener("click", function () {
      var confirmar = document.getElementById("kbConfirmExcluir");
      if (!confirmar) {
        confirmar = document.createElement("p");
        confirmar.id = "kbConfirmExcluir";
        confirmar.textContent = "Remover esta tarefa?";
        var sim = document.createElement("button");
        sim.type = "button";
        sim.className = "btn ghost";
        sim.textContent = "Excluir";
        sim.addEventListener("click", function () {
          post(drawerForm.dataset.del, {}).then(function () {
            toast("Tarefa removida");
            fecharDrawer();
            location.reload();
          }).catch(function (err) { toast(err.message); });
        });
        confirmar.appendChild(sim);
        btnDel.parentElement.appendChild(confirmar);
      }
    });
  }
})();
