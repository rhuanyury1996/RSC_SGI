/* Atividades: Lista, Quadro, Gantt e Mind Map sobre os mesmos dados. */
(function () {
  "use strict";

  var fonte = document.getElementById("ca-dados");
  var app = document.getElementById("caApp");
  if (!fonte || !app) return;
  var D = JSON.parse(fonte.textContent);
  var base = window.SGIAtividades || {};
  var toast = base.toast || function (t) { window.alert(t); };

  // ------------------------------------------------------------------ dados
  var STATUS = {
    nao_iniciado: { cor: "#FFC53D", texto: "#5C4300", tipo: "aberto" },
    organizando: { cor: "#0091FF", texto: "#fff", tipo: "ativo" },
    executando: { cor: "#0091FF", texto: "#fff", tipo: "ativo" },
    em_revisao: { cor: "#FFC53D", texto: "#5C4300", tipo: "ativo" },
    liberado: { cor: "#1090E0", texto: "#fff", tipo: "ativo" },
    realizado: { cor: "#30A46C", texto: "#fff", tipo: "concluido" },
    complete: { cor: "#008844", texto: "#fff", tipo: "fechado" },
  };
  var FLUXO = D.status.map(function (s) { return s.valor; });
  // Cores e nomes vêm do admin; o texto da pílula se ajusta ao contraste.
  function textoSobre(cor) {
    var m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(cor || "");
    if (!m) return "#fff";
    var lum = (0.299 * parseInt(m[1], 16) + 0.587 * parseInt(m[2], 16) + 0.114 * parseInt(m[3], 16)) / 255;
    return lum > 0.62 ? "#3b3200" : "#fff";
  }
  D.status.forEach(function (s) {
    STATUS[s.valor].label = s.label;
    if (s.cor) { STATUS[s.valor].cor = s.cor; STATUS[s.valor].texto = textoSobre(s.cor); }
  });
  var PRIO = {
    urgente: { cor: "#F50000" },
    alta: { cor: "#FFCC00" },
    media: { cor: "#6FDDFF" },
    baixa: { cor: "#D8D8D8" },
    nenhuma: { cor: "" },
  };
  var PRIO_ORDEM = D.prioridades.map(function (p) { return p.valor; });
  D.prioridades.forEach(function (p) {
    PRIO[p.valor].label = p.label;
    if (p.cor && p.valor !== "nenhuma") PRIO[p.valor].cor = p.cor;
  });
  var PALETA = ["#7B68EE", "#FF7800", "#1090E0", "#2EA52C", "#D6409F", "#00A3BF", "#E5484D", "#AB6400"];
  var PESSOAS = {};
  D.pessoas.forEach(function (p, i) {
    p.cor = p.ativo ? PALETA[i % PALETA.length] : "#B9BEC7";
    PESSOAS[p.id] = p;
  });
  var EMPRESAS = {};
  D.empresas.forEach(function (e) { EMPRESAS[e.id] = e; });
  var HOJE = D.hoje;

  var S = {
    tarefas: D.tarefas,
    visao: D.visao,
    busca: "",
    agrupar: "status",
    subs: false,
    abertas: {},
    fechadas: false,
    pessoas: [],
    eu: false,
    escala: "semana",
    mapaGrupo: "empresa",
    mapaFechados: {},
    recolhidos: {},
    drawer: null,
  };

  (function lerUrl() {
    var q = new URLSearchParams(location.search);
    if (!q.get("org")) {
      try {
        var salvo = localStorage.getItem("sgi-atividades-visao");
        if (["lista", "quadro", "gantt", "mapa"].indexOf(salvo) >= 0) S.visao = salvo;
      } catch (e) { /* sem storage */ }
    }
    S.busca = q.get("q") || "";
    if (["status", "pessoa", "prioridade", "empresa"].indexOf(q.get("agrupar")) >= 0) S.agrupar = q.get("agrupar");
    S.fechadas = q.get("fechadas") === "1";
    S.eu = q.get("eu") === "1";
    S.subs = q.get("subs") === "1";
    S.pessoas = (q.get("pessoas") || "").split(",").filter(Boolean).map(Number);
  })();

  function salvarUrl() {
    var q = new URLSearchParams();
    q.set("org", S.visao);
    if (S.busca) q.set("q", S.busca);
    if (S.agrupar !== "status") q.set("agrupar", S.agrupar);
    if (S.fechadas) q.set("fechadas", "1");
    if (S.eu) q.set("eu", "1");
    if (S.subs) q.set("subs", "1");
    if (S.pessoas.length) q.set("pessoas", S.pessoas.join(","));
    history.replaceState(null, "", location.pathname + "?" + q.toString());
    try { localStorage.setItem("sgi-atividades-visao", S.visao); } catch (e) { /* sem storage */ }
  }

  // ---------------------------------------------------------------- helpers
  function h(tag, attrs) {
    var el = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        if (k === "class") el.className = v;
        else if (k === "text") el.textContent = v;
        else if (k === "style" && typeof v === "object") {
          Object.keys(v).forEach(function (p) {
            if (p.slice(0, 2) === "--") el.style.setProperty(p, v[p]);
            else el.style[p] = v[p];
          });
        }
        else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
        else if (k === "dataset") Object.keys(v).forEach(function (d) { el.dataset[d] = v[d]; });
        else el.setAttribute(k, v === true ? "" : v);
      });
    }
    for (var i = 2; i < arguments.length; i++) anexar(el, arguments[i]);
    return el;
  }
  function anexar(el, filho) {
    if (filho === null || filho === undefined || filho === false) return;
    if (Array.isArray(filho)) { filho.forEach(function (f) { anexar(el, f); }); return; }
    el.appendChild(typeof filho === "string" || typeof filho === "number" ? document.createTextNode(String(filho)) : filho);
  }

  var ICONES = {
    flag: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
    flagCheia: '<path d="M5 21V4" /><path d="M5 4h11l-2 4 2 4H5z" fill="currentColor"/>',
    calendario: '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M3 9h18M8 2v4M16 2v4"/>',
    mais: '<path d="M12 5v14M5 12h14"/>',
    seta: '<path d="M9 6l6 6-6 6"/>',
    setaBaixo: '<path d="M6 9l6 6 6-6"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    x: '<path d="M6 6l12 12M18 6L6 18"/>',
    grip: '<circle cx="9" cy="6" r="1.2" fill="currentColor"/><circle cx="15" cy="6" r="1.2" fill="currentColor"/><circle cx="9" cy="12" r="1.2" fill="currentColor"/><circle cx="15" cy="12" r="1.2" fill="currentColor"/><circle cx="9" cy="18" r="1.2" fill="currentColor"/><circle cx="15" cy="18" r="1.2" fill="currentColor"/>',
    lapis: '<path d="M4 20h4L19 9l-4-4L4 16v4z"/>',
    sub: '<path d="M6 4v9a3 3 0 003 3h10M15 12l4 4-4 4"/>',
    abrir: '<path d="M14 4h6v6M20 4l-8 8M10 5H5v14h14v-5"/>',
    play: '<path d="M7 5l12 7-12 7z" fill="currentColor"/>',
    pause: '<path d="M8 5v14M16 5v14"/>',
    lixo: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
    alerta: '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/>',
    pessoa: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
    lista: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    menos: '<path d="M5 12h14"/>',
    ajustar: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    relogio: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    relogioMais: '<circle cx="11" cy="13" r="8"/><path d="M11 9v4l2.5 1.5M19 2v5M16.5 4.5h5"/>',
    dots: '<circle cx="5" cy="12" r="1.4" fill="currentColor"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/><circle cx="19" cy="12" r="1.4" fill="currentColor"/>',
    desfazer: '<path d="M9 14L4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 010 11H11"/>',
  };
  function icone(nome, classe) {
    var span = document.createElement("span");
    span.className = "ca-ico" + (classe ? " " + classe : "");
    span.setAttribute("aria-hidden", "true");
    span.innerHTML = '<svg viewBox="0 0 24 24">' + ICONES[nome] + "</svg>";
    return span;
  }

  var MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  var MESES_LONGOS = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];
  function parseData(iso) {
    if (!iso) return null;
    var p = iso.split("-");
    return new Date(Date.UTC(+p[0], +p[1] - 1, +p[2]));
  }
  function isoDe(d) { return d.toISOString().slice(0, 10); }
  function somarDias(d, n) { return new Date(d.getTime() + n * 86400000); }
  function diasEntre(a, b) { return Math.round((b.getTime() - a.getTime()) / 86400000); }
  function fmtData(iso) {
    var d = parseData(iso);
    if (!d) return "";
    var txt = d.getUTCDate() + " " + MESES[d.getUTCMonth()];
    if (d.getUTCFullYear() !== parseData(HOJE).getUTCFullYear()) txt += " " + String(d.getUTCFullYear()).slice(2);
    return txt;
  }
  function fmtTempo(seg) {
    seg = Math.max(0, Math.floor(seg || 0));
    var hh = Math.floor(seg / 3600);
    var mm = Math.floor((seg % 3600) / 60);
    var ss = seg % 60;
    return hh + ":" + (mm < 10 ? "0" : "") + mm + ":" + (ss < 10 ? "0" : "") + ss;
  }
  function normalizar(t) {
    return (t || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  }

  function csrf() {
    var m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    if (m) return decodeURIComponent(m[1]);
    var i = document.querySelector("input[name=csrfmiddlewaretoken]");
    return i ? i.value : "";
  }
  function post(url, campos) {
    var body = new FormData();
    body.append("csrfmiddlewaretoken", csrf());
    Object.keys(campos || {}).forEach(function (k) {
      var v = campos[k];
      if (v === undefined || v === null) return;
      if (Array.isArray(v)) v.forEach(function (x) { body.append(k, x); });
      else body.append(k, v);
    });
    return fetch(url, {
      method: "POST",
      body: body,
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok || data.ok === false) throw new Error(data.erro || "Não foi possível salvar.");
        return data;
      });
    });
  }
  var URL_T = {
    status: function (id) { return "/atividades/" + id + "/status/"; },
    campos: function (id) { return "/atividades/" + id + "/campos/"; },
    timer: function (id) { return "/atividades/" + id + "/cronometro/"; },
    detalhe: function (id) { return "/atividades/" + id + "/"; },
    comentar: function (id) { return "/atividades/" + id + "/comentario/"; },
    sub: function (id) { return "/atividades/" + id + "/subtarefa/"; },
    excluir: function (id) { return "/atividades/" + id + "/excluir/"; },
    restaurar: function (id) { return "/atividades/" + id + "/restaurar/"; },
    tempoLancar: function (id) { return "/atividades/" + id + "/tempo/"; },
    tempoEditar: function (sid) { return "/atividades/tempo/" + sid + "/"; },
    tempoExcluir: function (sid) { return "/atividades/tempo/" + sid + "/excluir/"; },
  };

  // ----------------------------------------------------------- estado/tarefas
  function todas() {
    var out = [];
    S.tarefas.forEach(function (t) {
      out.push(t);
      (t.subtarefas || []).forEach(function (s) { out.push(s); });
    });
    return out;
  }
  function achar(id) {
    id = Number(id);
    var lista = todas();
    for (var i = 0; i < lista.length; i++) if (lista[i].id === id) return lista[i];
    return null;
  }
  function pai(t) { return t && t.pai ? achar(t.pai) : null; }
  function substituir(nova) {
    if (!nova) return;
    if (nova.pai) {
      var p = achar(nova.pai);
      if (!p) return;
      p.subtarefas = (p.subtarefas || []).map(function (s) { return s.id === nova.id ? nova : s; });
      if (!p.subtarefas.some(function (s) { return s.id === nova.id; })) p.subtarefas.push(nova);
      return;
    }
    var achou = false;
    S.tarefas = S.tarefas.map(function (t) {
      if (t.id === nova.id) { achou = true; return nova; }
      return t;
    });
    if (!achou) S.tarefas.unshift(nova);
  }
  function remover(id) {
    S.tarefas = S.tarefas.filter(function (t) { return t.id !== id; });
    S.tarefas.forEach(function (t) {
      if (t.subtarefas) t.subtarefas = t.subtarefas.filter(function (s) { return s.id !== id; });
    });
  }
  function recarregar() {
    return fetch(location.pathname + "?formato=json", { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (data) { if (data && data.tarefas) { S.tarefas = data.tarefas; render(); } });
  }

  function membros(t) {
    var ids = [t.responsavel].concat(t.participantes || []);
    return ids.filter(function (id, i) { return id && ids.indexOf(id) === i; });
  }
  function concluida(t) { return t.status === "realizado" || t.status === "complete"; }
  function atrasoDias(t) {
    if (!t.atraso) return 0;
    var ref = t.entrega && t.entrega < HOJE ? t.entrega : t.atraso;
    return diasEntre(parseData(ref), parseData(HOJE));
  }
  function vencida(t) { return !concluida(t) && !!t.entrega && t.entrega < HOJE; }

  function passaFiltro(t) {
    if (!S.fechadas && concluida(t)) return false;
    var subs = t.subtarefas || [];
    if (S.busca) {
      var b = normalizar(S.busca);
      var bate = normalizar(t.titulo).indexOf(b) >= 0 || subs.some(function (s) { return normalizar(s.titulo).indexOf(b) >= 0; });
      if (!bate) return false;
    }
    var gente = membros(t);
    subs.forEach(function (s) { gente = gente.concat(membros(s)); });
    if (S.eu && gente.indexOf(D.eu) < 0) return false;
    if (S.pessoas.length && !S.pessoas.some(function (p) { return gente.indexOf(p) >= 0; })) return false;
    return true;
  }
  function visiveis() {
    return S.tarefas.filter(passaFiltro).slice().sort(function (a, b) { return a.ordem - b.ordem; });
  }

  function grupos(lista, modo) {
    var mapa = {};
    var ordem = [];
    function bucket(chave, meta) {
      if (!mapa[chave]) { mapa[chave] = Object.assign({ chave: chave, itens: [] }, meta); ordem.push(chave); }
      return mapa[chave];
    }
    if (modo === "status") {
      FLUXO.forEach(function (s) { bucket(s, { label: STATUS[s].label, cor: STATUS[s].cor, texto: STATUS[s].texto, status: s }); });
      lista.forEach(function (t) { mapa[t.status].itens.push(t); });
      return ordem.map(function (k) { return mapa[k]; }).filter(function (g) { return g.itens.length; });
    }
    if (modo === "prioridade") {
      PRIO_ORDEM.forEach(function (p) { bucket(p, { label: PRIO[p].label, cor: PRIO[p].cor || "#B9BEC7", texto: textoSobre(PRIO[p].cor || "#B9BEC7"), prioridade: p }); });
      lista.forEach(function (t) { mapa[t.prioridade].itens.push(t); });
      return ordem.map(function (k) { return mapa[k]; }).filter(function (g) { return g.itens.length; });
    }
    if (modo === "pessoa") {
      lista.forEach(function (t) {
        var p = PESSOAS[t.responsavel] || { nome: "Sem responsável", cor: "#B9BEC7" };
        bucket("p" + t.responsavel, { label: p.nome, cor: p.cor, texto: "#fff", pessoa: t.responsavel }).itens.push(t);
      });
      return ordem.map(function (k) { return mapa[k]; }).sort(function (a, b) { return a.label.localeCompare(b.label); });
    }
    lista.forEach(function (t) {
      var e = EMPRESAS[t.empresa];
      bucket("e" + (t.empresa || 0), { label: e ? e.nome : "Sem empresa", cor: "#656F7D", texto: "#fff", empresa: t.empresa || "" }).itens.push(t);
    });
    return ordem.map(function (k) { return mapa[k]; }).sort(function (a, b) {
      if (!a.empresa) return 1;
      if (!b.empresa) return -1;
      return a.label.localeCompare(b.label);
    });
  }

  // ------------------------------------------------------------ peças comuns
  function pill(status, extra) {
    var s = STATUS[status];
    return h("span", { class: "ca-pill" + (extra ? " " + extra : ""), style: { background: s.cor, color: s.texto } }, s.label);
  }
  function avatar(id, pequeno) {
    var p = PESSOAS[id];
    if (!p) return null;
    var el = h("span", { class: "ca-av" + (pequeno ? " is-sm" : "") + (p.ativo ? "" : " is-off"), style: { background: p.cor }, title: p.nome + (p.ativo ? "" : " (desativado)") });
    if (p.ativo) el.textContent = p.iniciais;
    else el.appendChild(icone("pessoa"));
    return el;
  }
  function avatares(t, max) {
    max = max || 3;
    var ids = membros(t);
    var box = h("span", { class: "ca-avs", title: ids.map(function (id) { return PESSOAS[id] ? PESSOAS[id].nome : ""; }).join(", ") });
    ids.slice(0, max).forEach(function (id) { anexar(box, avatar(id)); });
    if (ids.length > max) anexar(box, h("span", { class: "ca-av ca-av-more" }, "+" + (ids.length - max)));
    return box;
  }
  function bandeira(prio) {
    var p = PRIO[prio] || PRIO.nenhuma;
    var vazia = !p.cor || prio === "nenhuma";
    var el = icone(vazia ? "flag" : "flagCheia", "ca-flag" + (vazia ? " is-empty" : ""));
    if (!vazia) el.style.color = p.cor;
    return el;
  }
  function circuloStatus(t) {
    var s = STATUS[t.status];
    var el = h("span", { class: "ca-dot" + (concluida(t) ? " is-done" : ""), style: { "--c": s.cor } });
    if (concluida(t)) el.appendChild(icone("check"));
    return el;
  }
  function dataEl(t, opcoes) {
    opcoes = opcoes || {};
    if (!t.entrega) {
      return h("span", { class: "ca-date is-none" }, opcoes.icone ? icone("calendario") : null, opcoes.vazio || "");
    }
    var atras = vencida(t);
    var el = h("span", { class: "ca-date" + (atras ? " is-late" : "") }, opcoes.icone ? icone("calendario") : null, fmtData(t.entrega));
    if (atras) {
      var n = diasEntre(parseData(t.entrega), parseData(HOJE));
      el.dataset.tip = n === 1 ? "Venceu ontem" : "Venceu há " + n + " dias";
    } else if (t.entrega === HOJE) {
      el.dataset.tip = "Vence hoje";
    }
    return el;
  }
  function fmtCurto(seg) {
    seg = Math.max(0, Math.floor(seg || 0));
    var hh = Math.floor(seg / 3600);
    var mm = Math.floor((seg % 3600) / 60);
    if (hh) return hh + "h" + (mm < 10 ? "0" : "") + mm;
    if (mm) return mm + "min";
    return seg ? "<1min" : "0min";
  }
  function primeiroNome(id) {
    var p = PESSOAS[id];
    return p ? p.nome.split(" ")[0] : "Alguém";
  }
  function outrosRodando(t) {
    return (t.rodando || []).filter(function (r) { return r.id !== D.eu; });
  }
  function resumoPessoas(t) {
    var pp = t.por_pessoa || {};
    return Object.keys(pp).sort(function (a, b) { return pp[b] - pp[a]; })
      .map(function (id) { return primeiroNome(Number(id)) + " " + fmtCurto(pp[id]); }).join(" · ");
  }
  function timerBtn(t) {
    var meu = !!t.timer_inicio;
    var outros = outrosRodando(t);
    var vivo = meu || outros.length > 0;
    var seg = segundosAgora(t);
    var acao = meu ? "Pausar meu cronômetro" : "Iniciar meu cronômetro";
    var dica = [acao];
    if (outros.length) dica.push(outros.map(function (r) { return primeiroNome(r.id); }).join(" e ") + (outros.length === 1 ? " está" : " estão") + " cronometrando");
    var quem = resumoPessoas(t);
    if (quem) dica.push("Total " + fmtTempo(seg) + ": " + quem);
    var btn = h("button", {
      type: "button",
      class: "ca-timer" + (meu ? " is-running" : outros.length ? " is-others" : "") + (seg ? " has-time" : " is-zero"),
      "data-timer": t.id,
      title: dica.join("\n"),
      "aria-label": acao,
      onclick: function (ev) { ev.stopPropagation(); alternarTimer(t.id); },
    }, h("span", { class: "ca-timer-ico" }, icone(meu ? "pause" : "play")),
    h("span", { class: "ca-timer-txt" }, vivo ? fmtTempo(seg) : seg ? fmtCurto(seg) : "—"),
    outros.length ? h("span", { class: "ca-timer-quem" }, outros.slice(0, 2).map(function (r) { return avatar(r.id, true); })) : null);
    if (concluida(t) && !meu) btn.disabled = true;
    return btn;
  }
  function tempoTotal(t) {
    return segundosAgora(t) + (t.subtarefas || []).reduce(function (s, x) { return s + segundosAgora(x); }, 0);
  }
  function somaTempo(lista) {
    return lista.reduce(function (s, t) { return s + tempoTotal(t); }, 0);
  }
  function rodandoEm(lista) {
    var out = [];
    lista.forEach(function (t) {
      [t].concat(t.subtarefas || []).forEach(function (x) {
        (x.rodando || []).forEach(function (r) { out.push(r); });
      });
    });
    return out;
  }
  function segundosAgora(t) {
    var rodando = t.rodando || [];
    if (!rodando.length) return t.segundos || 0;
    // Total da equipe: base + cada sessão aberta (uma por pessoa).
    return (t.acumulado || 0) + rodando.reduce(function (s, r) {
      return s + Math.max(0, Math.floor((Date.now() - Date.parse(r.inicio)) / 1000));
    }, 0);
  }
  setInterval(function () {
    document.querySelectorAll(".ca-timer.is-running, .ca-timer.is-others").forEach(function (btn) {
      var t = achar(btn.getAttribute("data-timer"));
      var txt = btn.querySelector(".ca-timer-txt");
      if (t && txt) txt.textContent = fmtTempo(segundosAgora(t));
    });
    // Totais (grupos, resumo e painel) acompanham o cronômetro ao vivo.
    if (!document.querySelector(".ca-timer.is-running, .ca-timer.is-others")) return;
    document.querySelectorAll("[data-total]").forEach(function (el) {
      var ids = el.dataset.total.split(",").map(Number);
      var lista = ids.map(achar).filter(Boolean);
      el.textContent = fmtCurto(somaTempo(lista));
    });
  }, 1000);

  // ------------------------------------------------------------------ ações
  function aplicarResposta(data) {
    if (data && data.tarefa) substituir(data.tarefa);
    render();
    if (S.drawer) desenharDrawer();
  }
  function mudarStatus(id, status) {
    var t = achar(id);
    if (!t || t.status === status) return;
    if (!t.pode_status) { toast("Sem permissão para mudar o status desta tarefa."); return; }
    var antes = t.status;
    t.status = status;
    render();
    post(URL_T.status(id), { status: status }).then(function (data) {
      aplicarResposta(data);
      var nova = achar(id);
      if (nova && concluida(nova) && !concluida({ status: antes }) && !nova.pai && !S.fechadas) {
        toast("Tarefa concluída e oculta da lista", {
          label: "Desfazer",
          onClick: function () { mudarStatus(id, antes); },
        });
        return;
      }
      ofertaTimer(nova);
    }).catch(function (err) {
      t.status = antes;
      render();
      toast(err.message);
    });
  }
  function ofertaTimer(t) {
    if (!t) return;
    var label = STATUS[t.status].label;
    if (t.status === "executando" && !t.timer_inicio) {
      toast("Movida para " + label, { label: "Iniciar timer", onClick: function () { alternarTimer(t.id); } });
    } else {
      toast("Movida para " + label);
    }
  }
  function salvarCampos(id, campos, msg) {
    var t = achar(id);
    if (!t) return Promise.resolve();
    if (!t.pode_editar) { toast("Sem permissão para editar esta tarefa."); return Promise.resolve(); }
    return post(URL_T.campos(id), campos).then(function (data) {
      aplicarResposta(data);
      if (data.aviso) toast("Salvo. Atenção: " + data.aviso);
      else if (msg) toast(msg);
    }).catch(function (err) { toast(err.message); render(); });
  }
  function alternarTimer(id) {
    post(URL_T.timer(id), {}).then(function (data) {
      // O servidor pausa outros timers da pessoa: sincroniza tudo.
      if (data.tarefa) substituir(data.tarefa);
      render();
      if (S.drawer) desenharDrawer();
      var topo = window.SGITopbarTimer;
      if (topo) {
        if (data.ativo) topo.mostrar(id, data.titulo || "", URL_T.timer(id), data);
        else if (String(topo.pk()) === String(id)) topo.paint(data);
      }
      toast(data.ativo ? "Cronômetro iniciado" : "Cronômetro pausado");
      recarregar().then(function () {
        if (S.drawer) { desenharDrawer(); carregarDetalhe(S.drawer); }
      });
    }).catch(function (err) { toast(err.message); });
  }
  function criarRapida(titulo, extra) {
    var campos = Object.assign({ acao: "criar_rapida", titulo: titulo, responsavel: D.eu, prioridade: "media" }, extra || {});
    return post(D.urls.criar, campos).then(function (data) {
      if (data.tarefa) {
        var menor = S.tarefas.reduce(function (m, t) { return Math.min(m, t.ordem); }, 0);
        data.tarefa.ordem = menor - 1;
        substituir(data.tarefa);
      }
      render();
      toast(data.aviso ? "Tarefa adicionada. " + data.aviso : "Tarefa adicionada");
      return data.tarefa;
    }).catch(function (err) { toast(err.message); });
  }
  function excluir(id) {
    var t = achar(id);
    post(URL_T.excluir(id), {}).then(function () {
      remover(id);
      fecharDrawer();
      render();
      toast("Tarefa removida", {
        label: "Desfazer",
        onClick: function () {
          post(URL_T.restaurar(id), {}).then(function () { recarregar(); toast("Exclusão desfeita"); })
            .catch(function (err) { toast(err.message); });
        },
      });
    }).catch(function (err) { toast(err.message); });
    return t;
  }

  // Reordenar após arrastar (lista e quadro).
  function soltar(id, status, antesDeId) {
    var t = achar(id);
    if (!t || t.pai) return;
    var mudouStatus = t.status !== status;
    if (mudouStatus && !t.pode_status) { toast("Sem permissão para mudar o status desta tarefa."); return; }
    var copia = S.tarefas.map(function (x) { return { id: x.id, ordem: x.ordem, status: x.status }; });
    var coluna = visiveis().filter(function (x) { return x.status === status && x.id !== t.id; });
    var idx = antesDeId ? coluna.findIndex(function (x) { return x.id === Number(antesDeId); }) : -1;
    if (idx < 0) idx = coluna.length;
    coluna.splice(idx, 0, t);
    coluna.forEach(function (x, i) { x.ordem = i; });
    t.status = status;
    render();
    post(D.urls.reordenar, {
      ids: coluna.map(function (x) { return x.id; }),
      movida: mudouStatus ? t.id : "",
      status: mudouStatus ? status : "",
    }).then(function (data) {
      if (data.tarefa) {
        data.tarefa.ordem = t.ordem;
        substituir(data.tarefa);
        render();
      }
      if (mudouStatus) ofertaTimer(achar(id));
    }).catch(function (err) {
      copia.forEach(function (c) {
        var x = achar(c.id);
        if (x) { x.ordem = c.ordem; x.status = c.status; }
      });
      render();
      toast(err.message);
    });
  }

  // ------------------------------------------------------------------ menus
  var menu = document.getElementById("caMenu");
  var menuAncora = null;
  function abrirMenu(ancora, conteudo, largura) {
    fecharMenu();
    menu.innerHTML = "";
    anexar(menu, conteudo);
    menu.hidden = false;
    menu.style.minWidth = (largura || 200) + "px";
    var r = ancora.getBoundingClientRect();
    var mw = menu.offsetWidth;
    var mh = menu.offsetHeight;
    var x = Math.min(r.left, window.innerWidth - mw - 8);
    var y = r.bottom + 4;
    if (y + mh > window.innerHeight - 8) y = Math.max(8, r.top - mh - 4);
    menu.style.left = Math.max(8, x) + "px";
    menu.style.top = y + "px";
    menuAncora = ancora;
    var primeiro = menu.querySelector("button, input, select");
    if (primeiro) primeiro.focus({ preventScroll: true });
  }
  function fecharMenu() {
    if (menu.hidden) return;
    menu.hidden = true;
    menu.innerHTML = "";
    if (menuAncora && document.body.contains(menuAncora)) menuAncora.focus({ preventScroll: true });
    menuAncora = null;
  }
  document.addEventListener("mousedown", function (ev) {
    if (!menu.hidden && !menu.contains(ev.target) && ev.target !== menuAncora && !(menuAncora && menuAncora.contains(ev.target))) fecharMenu();
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") {
      if (!menu.hidden) { fecharMenu(); return; }
      if (S.drawer) fecharDrawer();
    }
  });
  window.addEventListener("resize", fecharMenu);
  document.addEventListener("scroll", function (ev) { if (!menu.contains(ev.target)) fecharMenu(); }, true);

  function itemMenu(conteudo, ativo, onclick, extra) {
    return h("button", { type: "button", role: "menuitem", class: "ca-menu-item" + (extra ? " " + extra : ""), onclick: function () { fecharMenu(); onclick(); } },
      conteudo, ativo ? icone("check", "ca-menu-check") : null);
  }
  function menuAcoes(ancora, t, opcoes) {
    opcoes = opcoes || {};
    var itens = [itemMenu([icone("abrir"), "Abrir"], false, function () { abrirDrawer(t.id); })];
    if (t.pode_editar && opcoes.renomear) itens.push(itemMenu([icone("lapis"), "Renomear"], false, opcoes.renomear));
    if (t.pode_editar && !t.pai) itens.push(itemMenu([icone("sub"), "Adicionar subtarefa"], false, function () { iniciarSubtarefa(t.id); }));
    if (t.pode_editar) itens.push(itemMenu([icone("calendario"), "Dia e horário no planner"], false, function () { setTimeout(function () { menuPlanner(ancora, t); }, 0); }));
    itens.push(itemMenu([icone("relogioMais"), "Lançar tempo"], false, function () { abrirLancamento(t.id); }));
    if (t.pode_status) {
      itens.push(concluida(t)
        ? itemMenu([icone("desfazer"), "Reabrir"], false, function () { mudarStatus(t.id, "nao_iniciado"); })
        : itemMenu([icone("check"), "Marcar como realizado"], false, function () { mudarStatus(t.id, "realizado"); }));
    }
    if (t.pode_editar) {
      itens.push(h("hr"));
      itens.push(itemMenu([icone("lixo"), "Excluir"], false, function () { excluir(t.id); }, "is-danger"));
    }
    abrirMenu(ancora, itens, 210);
  }
  function abrirLancamento(id) {
    S.formTempo = Number(id);
    S.focarTempo = true;
    abrirDrawer(id, "tempo");
  }
  function iniciarSubtarefa(id) {
    S.visao = S.visao === "lista" ? "lista" : S.visao;
    S.abertas[id] = true;
    S.addSub = Number(id);
    if (S.visao !== "lista") { abrirDrawer(id, "sub"); return; }
    render();
    var input = view.querySelector('.ca-subadd-input[data-pai="' + id + '"]');
    if (input) input.focus();
  }
  function menuStatus(ancora, t) {
    if (!t.pode_status) { toast("Sem permissão para mudar o status desta tarefa."); return; }
    abrirMenu(ancora, [
      h("p", { class: "ca-menu-title" }, "Status"),
      FLUXO.map(function (s) {
        return itemMenu([h("span", { class: "ca-dot", style: { "--c": STATUS[s].cor } }), STATUS[s].label], t.status === s, function () { mudarStatus(t.id, s); });
      }),
    ], 220);
  }
  function menuPrioridade(ancora, t) {
    if (!t.pode_editar) { toast("Sem permissão para editar esta tarefa."); return; }
    abrirMenu(ancora, [
      h("p", { class: "ca-menu-title" }, "Prioridade"),
      ["urgente", "alta", "media", "baixa"].map(function (p) {
        return itemMenu([bandeira(p), PRIO[p].label], t.prioridade === p, function () { salvarCampos(t.id, { prioridade: p }); });
      }),
      h("hr"),
      itemMenu([icone("x"), "Limpar"], false, function () { salvarCampos(t.id, { prioridade: "nenhuma" }); }),
    ], 190);
  }
  function menuData(ancora, t, campo) {
    campo = campo || "data_vencimento";
    if (!t.pode_editar) { toast("Sem permissão para editar esta tarefa."); return; }
    if (campo === "planejado_para") { menuPlanner(ancora, t); return; }
    var atual = t.vencimento || t.planejado;
    var input = h("input", { type: "date", class: "ca-input", value: atual || "", "aria-label": "Data" });
    function salvar(v) { fecharMenu(); salvarCampos(t.id, (function () { var o = {}; o[campo] = v; return o; })()); }
    input.addEventListener("change", function () { if (input.value) salvar(input.value); });
    var atalhos = [["Hoje", 0], ["Amanhã", 1], ["Em 1 semana", 7]];
    abrirMenu(ancora, [
      h("p", { class: "ca-menu-title" }, campo === "planejado_para" ? "Dia no planner" : "Data de entrega"),
      h("div", { class: "ca-menu-pad" }, input),
      atalhos.map(function (a) {
        return itemMenu(a[0], false, function () { salvar(isoDe(somarDias(parseData(HOJE), a[1]))); });
      }),
      h("hr"),
      itemMenu([icone("relogio"), "Dia e horário no planner…"], false, function () { setTimeout(function () { menuPlanner(ancora, t); }, 0); }),
      t.vencimento && campo === "data_vencimento" ? itemMenu([icone("x"), "Remover data de entrega"], false, function () { salvar(""); }) : null,
    ], 220);
  }
  function menuPlanner(ancora, t) {
    // Dia já passou (ou vazio) numa tarefa aberta: sugere hoje para entrar no planner.
    var sugerirHoje = !concluida(t) && (!t.planejado || t.planejado < HOJE);
    var dia = h("input", { type: "date", class: "ca-input", value: sugerirHoje ? HOJE : t.planejado, "aria-label": "Dia no planner" });
    var dica = sugerirHoje && t.planejado ? h("p", { class: "ca-menu-dica" }, "Estava em " + fmtData(t.planejado) + ". Sugerimos hoje para aparecer no planner do dia.") : null;
    var ini = h("input", { type: "time", class: "ca-input", value: t.hora_inicio || "", "aria-label": "Início", step: "300" });
    var fim = h("input", { type: "time", class: "ca-input", value: t.hora_fim || "", "aria-label": "Fim", step: "300" });
    var erro = h("p", { class: "ca-menu-erro", role: "alert" });
    function salvar(campos) {
      fecharMenu();
      salvarCampos(t.id, campos, "Planner atualizado");
    }
    // Ao escolher o início, sugere 1h de duração se o fim estiver vazio.
    ini.addEventListener("change", function () {
      if (ini.value && !fim.value) {
        var p = ini.value.split(":");
        var hh = Math.min(23, Number(p[0]) + 1);
        fim.value = (hh < 10 ? "0" : "") + hh + ":" + p[1];
      }
    });
    var form = h("form", { class: "ca-menu-form" },
      h("label", { class: "ca-menu-lbl" }, "Dia", dia),
      dica,
      h("div", { class: "ca-menu-horas" },
        h("label", { class: "ca-menu-lbl" }, "Início", ini),
        h("label", { class: "ca-menu-lbl" }, "Fim", fim)),
      erro,
      h("div", { class: "ca-menu-acoes" },
        h("button", { type: "submit", class: "ca-primary is-sm" }, "Salvar"),
        t.hora_inicio ? h("button", { type: "button", class: "ca-ghost is-sm", onclick: function () { salvar({ hora_inicio: "", hora_fim: "" }); } }, "Tirar horário") : null));
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      if (fim.value && !ini.value) { erro.textContent = "Informe o início."; return; }
      if (ini.value && fim.value && fim.value <= ini.value) { erro.textContent = "O fim deve ser depois do início."; return; }
      salvar({ planejado_para: dia.value, hora_inicio: ini.value, hora_fim: fim.value });
    });
    abrirMenu(ancora, [
      h("p", { class: "ca-menu-title" }, "Dia e horário no planner"),
      form,
      h("hr"),
      [["Hoje", 0], ["Amanhã", 1], ["Em 1 semana", 7]].map(function (a) {
        return itemMenu(a[0], false, function () { salvar({ planejado_para: isoDe(somarDias(parseData(HOJE), a[1])) }); });
      }),
    ], 250);
  }
  function menuPessoas(ancora, t) {
    if (!t.pode_editar) { toast("Sem permissão para editar esta tarefa."); return; }
    var sel = new Set(t.participantes || []);
    var lista = D.pessoas.filter(function (p) { return p.ativo || sel.has(p.id) || p.id === t.responsavel; });
    abrirMenu(ancora, [
      h("p", { class: "ca-menu-title" }, "Responsável principal"),
      D.pode_dirigir
        ? h("div", { class: "ca-menu-pad" }, h("select", {
          class: "ca-input",
          "aria-label": "Responsável principal",
          onchange: function (ev) { fecharMenu(); salvarCampos(t.id, { responsavel: ev.target.value }); },
        }, lista.filter(function (p) { return p.ativo; }).map(function (p) {
          return h("option", { value: p.id, selected: p.id === t.responsavel }, p.nome);
        })))
        : h("p", { class: "ca-menu-note" }, (PESSOAS[t.responsavel] || {}).nome || ""),
      h("p", { class: "ca-menu-title" }, "Outros responsáveis"),
      h("div", { class: "ca-menu-scroll" }, lista.filter(function (p) { return p.id !== t.responsavel; }).map(function (p) {
        var cb = h("input", { type: "checkbox", checked: sel.has(p.id) });
        cb.addEventListener("change", function () {
          if (cb.checked) sel.add(p.id); else sel.delete(p.id);
          salvarCampos(t.id, { participantes_enviados: "1", participantes: Array.from(sel) });
        });
        return h("label", { class: "ca-menu-item ca-menu-check-row" }, cb, avatar(p.id, true), p.nome);
      })),
    ], 240);
  }

  // ------------------------------------------------------------- moldura
  var view = document.getElementById("caView");
  var foot = document.getElementById("caFoot");
  var busca = document.getElementById("caBusca");
  busca.value = S.busca;
  var tBusca;
  busca.addEventListener("input", function () {
    clearTimeout(tBusca);
    tBusca = setTimeout(function () { S.busca = busca.value.trim(); salvarUrl(); render(); }, 120);
  });
  var ROTULO_AGRUPAR = { status: "Status", pessoa: "Responsável", prioridade: "Prioridade", empresa: "Empresa" };
  var btnAgrupar = document.getElementById("caAgrupar");
  btnAgrupar.addEventListener("click", function () {
    abrirMenu(btnAgrupar, [h("p", { class: "ca-menu-title" }, "Agrupar por"), Object.keys(ROTULO_AGRUPAR).map(function (k) {
      return itemMenu(ROTULO_AGRUPAR[k], S.agrupar === k, function () { S.agrupar = k; salvarUrl(); render(); });
    })]);
  });
  var btnSubs = document.getElementById("caSubs");
  btnSubs.addEventListener("click", function () { S.subs = !S.subs; S.abertas = {}; salvarUrl(); render(); });
  var btnFechadas = document.getElementById("caFechadas");
  btnFechadas.addEventListener("click", function () { S.fechadas = !S.fechadas; salvarUrl(); render(); });
  var btnEu = document.getElementById("caEu");
  btnEu.addEventListener("click", function () { S.eu = !S.eu; salvarUrl(); render(); });
  var btnResp = document.getElementById("caResp");
  btnResp.addEventListener("click", function () {
    var ativos = D.pessoas.filter(function (p) { return p.ativo; });
    abrirMenu(btnResp, [
      h("p", { class: "ca-menu-title" }, "Filtrar por responsável"),
      h("div", { class: "ca-menu-scroll" }, ativos.map(function (p) {
        var cb = h("input", { type: "checkbox", checked: S.pessoas.indexOf(p.id) >= 0 });
        cb.addEventListener("change", function () {
          S.pessoas = cb.checked ? S.pessoas.concat([p.id]) : S.pessoas.filter(function (x) { return x !== p.id; });
          salvarUrl();
          render();
        });
        return h("label", { class: "ca-menu-item ca-menu-check-row" }, cb, avatar(p.id, true), p.nome);
      })),
      S.pessoas.length ? [h("hr"), itemMenu("Limpar filtro", false, function () { S.pessoas = []; salvarUrl(); render(); })] : null,
    ], 240);
  });
  var dialogo = document.getElementById("dialogTarefa");
  document.getElementById("caNova").addEventListener("click", function () { if (dialogo) dialogo.showModal(); });
  var btnMais = document.getElementById("caNovaMais");
  btnMais.addEventListener("click", function () {
    abrirMenu(btnMais, [
      itemMenu("Tarefa com todos os campos", false, function () { dialogo.showModal(); }),
      itemMenu("Adição rápida na lista", false, function () {
        S.visao = "lista";
        S.agrupar = "status";
        salvarUrl();
        render();
        var add = view.querySelector(".ca-add");
        if (add) add.click();
      }),
    ], 230);
  });
  var fecharDlg = document.getElementById("btnFecharTarefa");
  if (fecharDlg) fecharDlg.addEventListener("click", function () { dialogo.close(); });
  if (dialogo && dialogo.dataset.autoOpen === "1") { try { dialogo.showModal(); } catch (e) { /* ignore */ } }

  app.querySelectorAll(".ca-tab[data-visao]").forEach(function (a) {
    a.addEventListener("click", function (ev) {
      if (ev.metaKey || ev.ctrlKey || ev.shiftKey) return;
      ev.preventDefault();
      S.visao = a.dataset.visao;
      salvarUrl();
      render();
    });
  });

  function desenharMembros() {
    var box = document.getElementById("caMembers");
    if (!box) return;
    box.innerHTML = "";
    var vistos = {};
    S.tarefas.forEach(function (t) { if (t.status !== "complete") membros(t).forEach(function (id) { vistos[id] = (vistos[id] || 0) + 1; }); });
    var ids = Object.keys(vistos).map(Number).filter(function (id) { return PESSOAS[id] && PESSOAS[id].ativo; })
      .sort(function (a, b) { return vistos[b] - vistos[a]; });
    var wrap = h("span", { class: "ca-avs is-lg" });
    ids.slice(0, 6).forEach(function (id) { anexar(wrap, avatar(id)); });
    if (ids.length > 6) anexar(wrap, h("span", { class: "ca-av ca-av-more" }, "+" + (ids.length - 6)));
    box.appendChild(wrap);
  }

  function render() {
    app.dataset.visao = S.visao;
    app.querySelectorAll(".ca-tab[data-visao]").forEach(function (a) {
      var on = a.dataset.visao === S.visao;
      a.classList.toggle("is-active", on);
      if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    app.querySelectorAll("[data-so]").forEach(function (el) {
      el.hidden = el.dataset.so.split(" ").indexOf(S.visao) < 0;
    });
    btnAgrupar.textContent = "Agrupar: " + ROTULO_AGRUPAR[S.agrupar];
    btnSubs.textContent = "Subtarefas: " + (S.subs ? "expandidas" : "recolhidas");
    btnFechadas.textContent = "Concluídas: " + (S.fechadas ? "visíveis" : "ocultas");
    btnFechadas.classList.toggle("is-on", S.fechadas);
    btnEu.classList.toggle("is-on", S.eu);
    btnEu.setAttribute("aria-pressed", S.eu ? "true" : "false");
    btnResp.textContent = S.pessoas.length ? "Responsável · " + S.pessoas.length : "Responsável";
    btnResp.classList.toggle("is-on", S.pessoas.length > 0);
    desenharMembros();

    var scroll = view.firstElementChild ? lerScroll() : null;
    S.entrouGantt = view.dataset.visao !== "gantt";
    view.innerHTML = "";
    var lista = visiveis();
    desenharResumo(S.tarefas.filter(passaFiltroSemFechadas));
    if (S.visao === "quadro") renderQuadro(lista);
    else if (S.visao === "gantt") renderGantt(lista);
    else if (S.visao === "mapa") renderMapa(lista);
    else renderLista(lista);
    if (scroll && scroll.visao === S.visao) restaurarScroll(scroll);

    var fechadas = S.tarefas.filter(function (t) { return concluida(t) && passaFiltroSemFechadas(t); }).length;
    foot.textContent = lista.length + (lista.length === 1 ? " tarefa" : " tarefas") +
      (S.fechadas || !fechadas ? "" : " · " + fechadas + (fechadas === 1 ? " concluída oculta" : " concluídas ocultas")) +
      (S.busca || S.eu || S.pessoas.length ? " · com filtro" : "");
  }
  function desenharResumo(lista) {
    var box = document.getElementById("caResumo");
    if (!box) return;
    box.innerHTML = "";
    var abertas = lista.filter(function (t) { return !concluida(t); });
    var atrasadas = abertas.filter(vencida);
    var urgentes = abertas.filter(function (t) { return t.prioridade === "urgente"; });
    var rodando = rodandoEm(lista);
    var maisAntiga = atrasadas.reduce(function (m, t) { return !m || t.entrega < m ? t.entrega : m; }, "");
    function tile(rotulo, valor, sub, tom, extra) {
      return h("div", { class: "ca-stat" + (tom ? " is-" + tom : "") },
        h("span", { class: "ca-stat-lbl" }, rotulo),
        h("strong", Object.assign({ class: "ca-stat-val" }, extra || {}), valor),
        h("span", { class: "ca-stat-sub" }, sub));
    }
    box.appendChild(tile("Em aberto", String(abertas.length), (lista.length - abertas.length) + " concluída" + (lista.length - abertas.length === 1 ? "" : "s")));
    box.appendChild(tile("Atrasadas", String(atrasadas.length),
      maisAntiga ? "a mais antiga venceu há " + diasEntre(parseData(maisAntiga), parseData(HOJE)) + " dias" : "nenhuma em atraso",
      atrasadas.length ? "late" : ""));
    box.appendChild(tile("Urgentes em aberto", String(urgentes.length), urgentes.length ? "priorize estas primeiro" : "nada urgente", urgentes.length ? "warn" : ""));
    var tempoBox = tile("Tempo registrado", fmtCurto(somaTempo(lista)),
      rodando.length
        ? rodando.map(function (r) { return primeiroNome(r.id); }).filter(function (n, i, a) { return a.indexOf(n) === i; }).join(", ") + " cronometrando agora"
        : "nenhum cronômetro rodando",
      rodando.length ? "live" : "", { "data-total": lista.map(function (t) { return t.id; }).join(",") });
    box.appendChild(tempoBox);
  }
  function lerScroll() {
    var out = { visao: view.dataset.visao, nos: [] };
    view.querySelectorAll("[data-scroll]").forEach(function (el) {
      out.nos.push({ chave: el.dataset.scroll, x: el.scrollLeft, y: el.scrollTop });
    });
    return out;
  }
  function restaurarScroll(s) {
    s.nos.forEach(function (n) {
      var el = view.querySelector('[data-scroll="' + n.chave + '"]');
      if (el) { el.scrollLeft = n.x; el.scrollTop = n.y; }
    });
  }

  // ---------------------------------------------------------- adicionar
  function addInline(rotulo, extra, classe) {
    var btn = h("button", { type: "button", class: "ca-add" + (classe ? " " + classe : "") }, icone("mais"), rotulo);
    btn.addEventListener("click", function () {
      var input = h("input", { type: "text", class: "ca-add-input", placeholder: "Nome da tarefa e Enter", maxlength: "200", "aria-label": "Nome da nova tarefa" });
      var form = h("form", { class: "ca-add-form" + (classe ? " " + classe : "") }, input,
        h("button", { type: "submit", class: "ca-primary is-sm" }, "Salvar"),
        h("button", { type: "button", class: "ca-ghost is-sm", onclick: function () { form.replaceWith(btn); } }, "Cancelar"));
      form.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var titulo = input.value.trim();
        if (!titulo) return;
        input.disabled = true;
        criarRapida(titulo, extra).then(function () {
          var novo = view.querySelector('.ca-add[data-chave="' + btn.dataset.chave + '"]');
          if (novo) novo.click();
        });
      });
      input.addEventListener("keydown", function (ev) { if (ev.key === "Escape") { ev.stopPropagation(); form.replaceWith(btn); } });
      btn.replaceWith(form);
      input.focus();
    });
    return btn;
  }
  function extraDoGrupo(g) {
    var e = {};
    if (g.status) e.status = g.status;
    if (g.prioridade) e.prioridade = g.prioridade;
    if (g.pessoa && (D.pode_dirigir || g.pessoa === D.eu)) e.responsavel = g.pessoa;
    if (g.empresa) e.cliente_rsc = g.empresa;
    return e;
  }

  // ---------------------------------------------------------------- LISTA
  function renderLista(lista) {
    view.dataset.visao = "lista";
    var wrap = h("div", { class: "ca-list", "data-scroll": "lista" });
    wrap.appendChild(h("div", { class: "ca-list-head", role: "row" },
      h("span", { class: "c-nome" }, "Nome"),
      h("span", { class: "c-resp" }, "Responsável"),
      h("span", { class: "c-data" }, "Data de entrega"),
      h("span", { class: "c-prio" }, "Prioridade"),
      h("span", { class: "c-tempo" }, "Tempo")));
    var gs = grupos(lista, S.agrupar);
    if (!gs.length) wrap.appendChild(vazio());
    gs.forEach(function (g) {
      var chaveRec = "lista:" + S.agrupar + ":" + g.chave;
      var fechado = !!S.recolhidos[chaveRec];
      var sec = h("section", { class: "ca-group" + (fechado ? " is-collapsed" : "") });
      var cab = h("header", { class: "ca-group-head" },
        h("button", {
          type: "button",
          class: "ca-caret",
          "aria-expanded": fechado ? "false" : "true",
          "aria-label": (fechado ? "Expandir " : "Recolher ") + g.label,
          onclick: function () { S.recolhidos[chaveRec] = !fechado; render(); },
        }, icone("setaBaixo")),
        S.agrupar === "pessoa" && g.pessoa ? avatar(g.pessoa) : null,
        h("span", { class: "ca-pill", style: { background: g.cor, color: g.texto } }, g.label),
        h("span", { class: "ca-count" }, g.itens.length));
      var totalGrupo = somaTempo(g.itens);
      sec.appendChild(h("div", { class: "ca-group-bar" }, cab,
        h("span", { class: "ca-group-time" + (totalGrupo ? "" : " is-zero"), title: "Tempo registrado no grupo" },
          icone("relogio"), h("span", { "data-total": g.itens.map(function (t) { return t.id; }).join(",") }, fmtCurto(totalGrupo)))));
      if (!fechado) {
        var corpo = h("div", { class: "ca-rows", "data-status": g.status || "" });
        g.itens.forEach(function (t) {
          corpo.appendChild(linha(t, false, g));
          var subs = t.subtarefas || [];
          var aberta = S.subs || S.abertas[t.id];
          if (subs.length && aberta) subs.forEach(function (s) { corpo.appendChild(linha(s, true, g)); });
          if (t.pode_editar && (aberta && subs.length || S.addSub === t.id)) corpo.appendChild(linhaNovaSub(t));
        });
        if (S.agrupar === "status") arrastavelLista(corpo, g.status);
        sec.appendChild(corpo);
        var add = addInline("Adicionar tarefa", extraDoGrupo(g));
        add.dataset.chave = chaveRec;
        sec.appendChild(add);
      }
      wrap.appendChild(sec);
    });
    view.appendChild(wrap);
  }
  function vazio() {
    var filtrando = S.busca || S.eu || S.pessoas.length;
    return h("div", { class: "ca-empty" },
      h("strong", null, filtrando ? "Nenhuma tarefa com esse filtro." : "Nenhuma tarefa por aqui."),
      h("span", null, filtrando ? "Limpe a busca ou os filtros para ver todas." : "Use “+ Tarefa” para criar a primeira."));
  }
  function linha(t, ehSub, g) {
    var row = h("div", {
      class: "ca-row" + (ehSub ? " is-sub" : "") + (concluida(t) ? " is-done" : ""),
      "data-id": t.id,
      role: "row",
    });
    var nome = h("div", { class: "c-nome" });
    if (!ehSub && S.agrupar === "status" && t.pode_status) {
      nome.appendChild(h("span", { class: "ca-grip", title: "Arrastar" }, icone("grip")));
      row.draggable = true;
    } else {
      nome.appendChild(h("span", { class: "ca-grip is-off" }));
    }
    var dot = h("button", { type: "button", class: "ca-dot-btn", "aria-label": "Status: " + STATUS[t.status].label, onclick: function (ev) { ev.stopPropagation(); menuStatus(dot, t); } }, circuloStatus(t));
    nome.appendChild(dot);
    var subs = t.subtarefas || [];
    var titulo = h("button", { type: "button", class: "ca-name", onclick: function () { abrirDrawer(t.id); } }, t.titulo);
    nome.appendChild(titulo);
    if (subs.length && !ehSub) {
      var aberto = S.subs || S.abertas[t.id];
      nome.appendChild(h("button", {
        type: "button",
        class: "ca-subcount" + (aberto ? " is-open" : ""),
        title: aberto ? "Recolher subtarefas" : "Mostrar subtarefas",
        onclick: function (ev) { ev.stopPropagation(); S.abertas[t.id] = !aberto; if (S.subs && aberto) { S.subs = false; salvarUrl(); } render(); },
      }, icone("sub"), subs.filter(concluida).length + "/" + subs.length));
    }
    var acoes = h("span", { class: "ca-quick" });
    if (t.pode_status && !concluida(t)) {
      acoes.appendChild(h("button", { type: "button", class: "ca-icon-btn is-ok", "data-tip": "Marcar como realizado", "aria-label": "Marcar como realizado", onclick: function (ev) { ev.stopPropagation(); mudarStatus(t.id, "realizado"); } }, icone("check")));
    }
    if (t.pode_editar && !ehSub) {
      acoes.appendChild(h("button", { type: "button", class: "ca-icon-btn", "data-tip": "Adicionar subtarefa", "aria-label": "Adicionar subtarefa", onclick: function (ev) { ev.stopPropagation(); iniciarSubtarefa(t.id); } }, icone("sub")));
    }
    if (t.pode_editar) {
      var agendar = h("button", { type: "button", class: "ca-icon-btn", "data-tip": "Dia e horário no planner", "aria-label": "Dia e horário no planner", onclick: function (ev) { ev.stopPropagation(); menuPlanner(agendar, t); } }, icone("calendario"));
      acoes.appendChild(agendar);
    }
    acoes.appendChild(h("button", { type: "button", class: "ca-icon-btn", "data-tip": "Lançar tempo", "aria-label": "Lançar tempo", onclick: function (ev) { ev.stopPropagation(); abrirLancamento(t.id); } }, icone("relogioMais")));
    var mais = h("button", { type: "button", class: "ca-icon-btn", "data-tip": "Mais ações", "aria-label": "Mais ações", "aria-haspopup": "menu", onclick: function (ev) { ev.stopPropagation(); menuAcoes(mais, t, { renomear: function () { renomear(titulo, t); } }); } }, icone("dots"));
    acoes.appendChild(mais);
    nome.appendChild(acoes);
    row.appendChild(nome);

    var resp = h("button", { type: "button", class: "c-resp ca-cell", "aria-label": "Responsáveis", onclick: function () { menuPessoas(resp, t); } }, avatares(t));
    row.appendChild(resp);
    var data = h("button", { type: "button", class: "c-data ca-cell", "aria-label": "Data de entrega", onclick: function () { menuData(data, t); } }, dataEl(t, { icone: !t.entrega, vazio: "" }));
    if (t.hora_inicio) {
      var hora = h("button", { type: "button", class: "ca-hora", "data-tip": "No planner: " + fmtData(t.planejado) + " · " + t.hora_inicio + (t.hora_fim ? "–" + t.hora_fim : ""), "aria-label": "Horário no planner", onclick: function (ev) { ev.stopPropagation(); menuPlanner(hora, t); } }, icone("relogio"), t.hora_inicio);
      nome.insertBefore(hora, acoes);
    }
    row.appendChild(data);
    var prio = h("button", { type: "button", class: "c-prio ca-cell", "aria-label": "Prioridade: " + PRIO[t.prioridade].label, onclick: function () { menuPrioridade(prio, t); } },
      bandeira(t.prioridade), t.prioridade !== "nenhuma" ? h("span", { class: "ca-prio-txt" }, PRIO[t.prioridade].label) : null);
    row.appendChild(prio);
    row.appendChild(h("div", { class: "c-tempo" }, timerBtn(t)));
    return row;
  }
  function linhaNovaSub(t) {
    var wrap = h("div", { class: "ca-subadd", "data-pai-row": t.id });
    if (S.addSub !== t.id) {
      wrap.appendChild(h("button", { type: "button", class: "ca-subadd-btn", onclick: function () { iniciarSubtarefa(t.id); } }, icone("mais"), "Adicionar subtarefa"));
      return wrap;
    }
    var input = h("input", { type: "text", class: "ca-subadd-input", "data-pai": t.id, placeholder: "Nome da subtarefa e Enter (Esc para sair)", maxlength: "200", "aria-label": "Nome da nova subtarefa" });
    input.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") { ev.stopPropagation(); S.addSub = null; render(); return; }
      if (ev.key !== "Enter") return;
      ev.preventDefault();
      var v = input.value.trim();
      if (!v) return;
      input.disabled = true;
      post(URL_T.sub(t.id), { titulo: v, responsavel: t.responsavel }).then(function (data) {
        if (data.pai) substituir(data.pai);
        S.abertas[t.id] = true;
        render();
        var novo = view.querySelector('.ca-subadd-input[data-pai="' + t.id + '"]');
        if (novo) novo.focus();
        toast("Subtarefa criada");
      }).catch(function (err) { input.disabled = false; toast(err.message); });
    });
    input.addEventListener("blur", function () {
      setTimeout(function () {
        if (S.addSub === t.id && !input.value.trim() && !input.disabled && document.activeElement !== input) { S.addSub = null; render(); }
      }, 150);
    });
    wrap.appendChild(h("span", { class: "ca-subadd-ico" }, icone("sub")));
    wrap.appendChild(input);
    return wrap;
  }
  function renomear(alvo, t) {
    var input = h("input", { type: "text", class: "ca-rename", value: t.titulo, maxlength: "200", "aria-label": "Nome da tarefa" });
    var feito = false;
    function fim(salvar) {
      if (feito) return;
      feito = true;
      var v = input.value.trim();
      if (salvar && v && v !== t.titulo) { t.titulo = v; salvarCampos(t.id, { titulo: v }); }
      else render();
    }
    input.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") { ev.preventDefault(); fim(true); }
      if (ev.key === "Escape") { ev.stopPropagation(); fim(false); }
    });
    input.addEventListener("blur", function () { fim(true); });
    alvo.replaceWith(input);
    input.focus();
    input.select();
  }

  // Arrastar (linhas e cards) com HTML5 drag and drop.
  var arrastando = null;
  function marcador() {
    var m = document.getElementById("caDropMark");
    if (!m) { m = h("div", { id: "caDropMark", class: "ca-drop-mark" }); }
    return m;
  }
  function itemAntes(container, y, seletor) {
    var itens = Array.prototype.slice.call(container.querySelectorAll(seletor)).filter(function (el) { return Number(el.dataset.id) !== arrastando; });
    for (var i = 0; i < itens.length; i++) {
      var r = itens[i].getBoundingClientRect();
      if (y < r.top + r.height / 2) return itens[i];
    }
    return null;
  }
  function ligarDrop(container, status, seletor, fimContainer) {
    container.addEventListener("dragover", function (ev) {
      if (arrastando === null) return;
      ev.preventDefault();
      ev.dataTransfer.dropEffect = "move";
      var antes = itemAntes(container, ev.clientY, seletor);
      var m = marcador();
      if (antes) container.insertBefore(m, antes);
      else if (fimContainer && fimContainer.parentNode === container) container.insertBefore(m, fimContainer);
      else container.appendChild(m);
      container.classList.add("is-over");
    });
    container.addEventListener("dragleave", function (ev) {
      if (!container.contains(ev.relatedTarget)) { container.classList.remove("is-over"); }
    });
    container.addEventListener("drop", function (ev) {
      ev.preventDefault();
      container.classList.remove("is-over");
      var antes = itemAntes(container, ev.clientY, seletor);
      var id = arrastando;
      arrastando = null;
      var m = document.getElementById("caDropMark");
      if (m) m.remove();
      if (id !== null) soltar(id, status, antes ? antes.dataset.id : null);
    });
  }
  function ligarDrag(el, id) {
    el.addEventListener("dragstart", function (ev) {
      arrastando = id;
      ev.dataTransfer.effectAllowed = "move";
      try { ev.dataTransfer.setData("text/plain", String(id)); } catch (e) { /* ignore */ }
      requestAnimationFrame(function () { el.classList.add("is-dragging"); });
    });
    el.addEventListener("dragend", function () {
      arrastando = null;
      el.classList.remove("is-dragging");
      var m = document.getElementById("caDropMark");
      if (m) m.remove();
      view.querySelectorAll(".is-over").forEach(function (x) { x.classList.remove("is-over"); });
    });
  }
  function arrastavelLista(corpo, status) {
    corpo.querySelectorAll(".ca-row[draggable=true]").forEach(function (row) { ligarDrag(row, Number(row.dataset.id)); });
    ligarDrop(corpo, status, ".ca-row:not(.is-sub)");
  }

  // ---------------------------------------------------------------- QUADRO
  function renderQuadro(lista) {
    view.dataset.visao = "quadro";
    var board = h("div", { class: "ca-board", "data-scroll": "quadro" });
    FLUXO.forEach(function (s) {
      var itens = lista.filter(function (t) { return t.status === s; });
      var meta = STATUS[s];
      var ehConcluida = s === "realizado" || s === "complete";
      var recolhida = ehConcluida ? !S.fechadas : !!S.recolhidos["quadro:" + s];
      if (recolhida) {
        var estreita = h("button", {
          type: "button",
          class: "ca-col is-collapsed",
          style: { "--c": meta.cor },
          "aria-label": "Expandir coluna " + meta.label,
          onclick: function () {
            if (ehConcluida) { S.fechadas = true; salvarUrl(); } else S.recolhidos["quadro:" + s] = false;
            render();
          },
        }, h("span", { class: "ca-col-vert" }, meta.label + " · " + (ehConcluida ? S.tarefas.filter(function (t) { return t.status === s && passaFiltroSemFechadas(t); }).length : itens.length)));
        ligarDrop(estreita, s, ".ca-card");
        board.appendChild(estreita);
        return;
      }
      var col = h("section", { class: "ca-col", style: { "--c": meta.cor }, "data-status": s });
      col.appendChild(h("header", { class: "ca-col-head" },
        h("span", { class: "ca-pill", style: { background: meta.cor, color: meta.texto } }, meta.label),
        h("span", { class: "ca-count" }, itens.length),
        h("span", { class: "ca-col-tools" },
          h("button", {
            type: "button", class: "ca-icon-btn", "data-tip": "Recolher", "aria-label": "Recolher coluna " + meta.label,
            onclick: function () {
              if (ehConcluida) { S.fechadas = false; salvarUrl(); } else S.recolhidos["quadro:" + s] = true;
              render();
            },
          }, icone("menos")),
          h("button", { type: "button", class: "ca-icon-btn", "data-tip": "Nova tarefa", "aria-label": "Nova tarefa em " + meta.label, onclick: function () { var a = col.querySelector(".ca-add"); if (a) a.click(); } }, icone("mais")))));
      var cards = h("div", { class: "ca-cards" });
      itens.forEach(function (t) { cards.appendChild(card(t)); });
      if (!itens.length) cards.appendChild(h("div", { class: "ca-col-empty" }, "Arraste tarefas para cá"));
      var add = addInline("Nova tarefa", { status: s }, "is-board");
      add.dataset.chave = "quadro:" + s;
      ligarDrop(cards, s, ".ca-card");
      col.appendChild(cards);
      col.appendChild(add);
      board.appendChild(col);
    });
    view.appendChild(board);
  }
  function passaFiltroSemFechadas(t) {
    var antes = S.fechadas;
    S.fechadas = true;
    var ok = passaFiltro(t);
    S.fechadas = antes;
    return ok;
  }
  function card(t) {
    var urg = t.prioridade === "urgente" && !concluida(t);
    var el = h("article", {
      class: "ca-card" + (urg ? " is-urgent" : "") + (concluida(t) ? " is-done" : ""),
      "data-id": t.id,
      tabindex: "0",
      "aria-label": t.titulo,
      draggable: t.pode_status ? "true" : null,
    });
    el.addEventListener("click", function (ev) { if (!ev.target.closest("button")) abrirDrawer(t.id); });
    el.addEventListener("keydown", function (ev) { if (ev.key === "Enter" && ev.target === el) abrirDrawer(t.id); });
    if (t.pode_status) ligarDrag(el, t.id);
    var emp = EMPRESAS[t.empresa];
    var maisCard = h("button", { type: "button", class: "ca-icon-btn ca-card-more", "aria-label": "Mais ações", "aria-haspopup": "menu", onclick: function (ev) { ev.stopPropagation(); menuAcoes(maisCard, t); } }, icone("dots"));
    el.appendChild(h("div", { class: "ca-card-top" }, h("p", { class: "ca-card-crumb" }, emp ? emp.nome : "Sem empresa"), maisCard));
    var tituloEl = h("p", { class: "ca-card-title" });
    if (concluida(t)) tituloEl.appendChild(icone("check", "ca-done-check"));
    tituloEl.appendChild(document.createTextNode(t.titulo));
    el.appendChild(tituloEl);
    var subs = t.subtarefas || [];
    var dataBtn = h("button", { type: "button", class: "ca-card-date", "aria-label": "Data de entrega", onclick: function () { menuData(dataBtn, t); } }, dataEl(t, { icone: true }));
    var prioBtn = h("button", { type: "button", class: "ca-card-flag", "aria-label": "Prioridade: " + PRIO[t.prioridade].label, onclick: function () { menuPrioridade(prioBtn, t); } }, bandeira(t.prioridade));
    var statusBtn = h("button", { type: "button", class: "ca-dot-btn", "aria-label": "Status: " + STATUS[t.status].label, onclick: function () { menuStatus(statusBtn, t); } }, circuloStatus(t));
    el.appendChild(h("div", { class: "ca-card-foot" },
      avatares(t),
      subs.length ? h("span", { class: "ca-subcount is-static", title: "Subtarefas" }, icone("sub"), subs.filter(concluida).length + "/" + subs.length) : null,
      h("span", { class: "ca-card-right" },
        timerBtn(t),
        dataBtn, prioBtn, statusBtn)));
    return el;
  }

  // ----------------------------------------------------------------- GANTT
  var ESCALAS = { dia: { px: 36, label: "Dia" }, semana: { px: 16, label: "Semana" }, mes: { px: 6, label: "Mês" } };
  function intervalo(t) {
    var ini = parseData(t.planejado);
    var fim = parseData(t.vencimento);
    if (ini && fim && ini < fim) return { ini: ini, fim: fim, barra: true };
    var d = parseData(t.entrega);
    return d ? { ini: d, fim: d, barra: false } : null;
  }
  function renderGantt(lista) {
    view.dataset.visao = "gantt";
    var esc = ESCALAS[S.escala];
    var hoje = parseData(HOJE);
    var minD = somarDias(hoje, -21);
    var maxD = somarDias(hoje, 21);
    lista.forEach(function (t) {
      var r = intervalo(t);
      if (!r) return;
      if (r.ini < minD) minD = r.ini;
      if (r.fim > maxD) maxD = r.fim;
    });
    var inicio = somarDias(minD, -((minD.getUTCDay() + 6) % 7) - 7);
    var fimD = somarDias(maxD, 14);
    var dias = diasEntre(inicio, fimD) + 1;
    var largura = dias * esc.px;
    var x = function (d) { return diasEntre(inicio, d) * esc.px; };

    var barra = h("div", { class: "ca-gantt-bar" },
      h("div", { class: "ca-seg", role: "group", "aria-label": "Escala" }, Object.keys(ESCALAS).map(function (k) {
        return h("button", { type: "button", class: S.escala === k ? "is-on" : "", "aria-pressed": S.escala === k ? "true" : "false", onclick: function () { S.escala = k; render(); setTimeout(irHoje, 0); } }, ESCALAS[k].label);
      })),
      h("button", { type: "button", class: "ca-ghost", onclick: function () { irHoje(); } }, "Hoje"),
      h("button", { type: "button", class: "ca-icon-btn is-boxed", "aria-label": "Voltar", onclick: function () { rolar(-1); } }, h("span", { class: "ca-flip" }, icone("seta"))),
      h("button", { type: "button", class: "ca-icon-btn is-boxed", "aria-label": "Avançar", onclick: function () { rolar(1); } }, icone("seta")),
      h("span", { class: "ca-gantt-hint" }, "Arraste um marco para mudar a data de entrega"));
    view.appendChild(barra);

    var scroller = h("div", { class: "ca-gantt", "data-scroll": "gantt", style: { "--w": largura + "px", "--dia": esc.px + "px" } });
    // Cabeçalho: meses + dias
    var head = h("div", { class: "ca-g-row ca-g-head" });
    head.appendChild(h("div", { class: "ca-g-left ca-g-cols" }, h("span", null, "Nome"), h("span", null, "Responsável"), h("span", null, "Entrega")));
    var tl = h("div", { class: "ca-g-time" });
    var meses = h("div", { class: "ca-g-months" });
    var diasRow = h("div", { class: "ca-g-days" });
    var cursor = new Date(inicio.getTime());
    while (cursor <= fimD) {
      var mIni = cursor;
      var prox = new Date(Date.UTC(cursor.getUTCFullYear(), cursor.getUTCMonth() + 1, 1));
      var mFim = prox > fimD ? somarDias(fimD, 1) : prox;
      meses.appendChild(h("span", { style: { left: x(mIni) + "px", width: (x(mFim) - x(mIni)) + "px" } }, MESES_LONGOS[mIni.getUTCMonth()] + " " + mIni.getUTCFullYear()));
      cursor = prox;
    }
    for (var i = 0; i < dias; i++) {
      var d = somarDias(inicio, i);
      var dow = d.getUTCDay();
      var mostra = S.escala === "dia" || (S.escala === "semana" && true) || (S.escala === "mes" && dow === 1);
      if (S.escala === "mes" && dow !== 1) continue;
      diasRow.appendChild(h("span", {
        class: (dow === 0 || dow === 6 ? "is-weekend" : "") + (isoDe(d) === HOJE ? " is-today" : ""),
        style: { left: x(d) + "px", width: (S.escala === "mes" ? 7 * esc.px : esc.px) + "px" },
      }, mostra ? String(d.getUTCDate()) : ""));
    }
    tl.appendChild(meses);
    tl.appendChild(diasRow);
    head.appendChild(tl);
    scroller.appendChild(head);

    var corpo = h("div", { class: "ca-g-body" });
    // Fundo: fins de semana e linha de hoje
    var fundo = h("div", { class: "ca-g-bg", "aria-hidden": "true" });
    if (S.escala !== "mes") {
      for (var j = 0; j < dias; j++) {
        var dd = somarDias(inicio, j);
        if (dd.getUTCDay() === 6) fundo.appendChild(h("span", { class: "ca-g-weekend", style: { left: x(dd) + "px", width: 2 * esc.px + "px" } }));
      }
    }
    fundo.appendChild(h("span", { class: "ca-g-today", style: { left: (x(hoje) + esc.px / 2) + "px" } }, h("b", null, "Hoje")));
    corpo.appendChild(fundo);

    var gs = grupos(lista, S.agrupar);
    if (!gs.length) corpo.appendChild(vazio());
    gs.forEach(function (g) {
      var chaveRec = "gantt:" + S.agrupar + ":" + g.chave;
      var fechado = !!S.recolhidos[chaveRec];
      corpo.appendChild(h("div", { class: "ca-g-row ca-g-group" },
        h("div", { class: "ca-g-left" },
          h("button", { type: "button", class: "ca-caret" + (fechado ? " is-closed" : ""), "aria-expanded": fechado ? "false" : "true", "aria-label": (fechado ? "Expandir " : "Recolher ") + g.label, onclick: function () { S.recolhidos[chaveRec] = !fechado; render(); } }, icone("setaBaixo")),
          h("span", { class: "ca-pill", style: { background: g.cor, color: g.texto } }, g.label),
          h("span", { class: "ca-count" }, g.itens.length)),
        h("div", { class: "ca-g-track" })));
      if (fechado) return;
      g.itens.forEach(function (t) {
        var row = h("div", { class: "ca-g-row ca-g-task" + (concluida(t) ? " is-done" : ""), "data-id": t.id });
        var nomeBtn = h("button", { type: "button", class: "ca-g-name", onclick: function () { abrirDrawer(t.id); } }, circuloStatus(t), h("span", null, t.titulo));
        row.appendChild(h("div", { class: "ca-g-left" }, nomeBtn,
          h("span", { class: "ca-g-resp" }, avatares(t, 2)),
          h("span", { class: "ca-g-ent" }, dataEl(t))));
        var track = h("div", { class: "ca-g-track" });
        var r = intervalo(t);
        if (!r) {
          var semData = h("button", { type: "button", class: "ca-g-nodate", style: { left: (x(hoje) + 12) + "px" }, onclick: function () { menuData(semData, t); } },
            h("span", null, "Sem datas"), h("span", { class: "ca-g-nodate-add" }, icone("mais"), "definir datas"));
          track.appendChild(semData);
        } else {
          var cor = STATUS[t.status].cor;
          var late = vencida(t);
          var marco;
          if (r.barra) {
            marco = h("button", {
              type: "button",
              class: "ca-g-barra" + (late ? " is-late" : ""),
              style: { left: x(r.ini) + 2 + "px", width: Math.max(esc.px, x(r.fim) - x(r.ini) + esc.px) - 4 + "px", background: cor },
              "aria-label": t.titulo + ": " + fmtData(isoDe(r.ini)) + " a " + fmtData(isoDe(r.fim)),
            });
          } else {
            marco = h("button", {
              type: "button",
              class: "ca-g-marco" + (late ? " is-late" : "") + (concluida(t) ? " is-done" : ""),
              style: { left: (x(r.ini) + esc.px / 2) + "px", "--c": cor },
              "aria-label": t.titulo + ": entrega " + fmtData(t.entrega),
            });
          }
          if (late) {
            var n = diasEntre(parseData(t.entrega), hoje);
            marco.dataset.tip = "Venceu há " + n + (n === 1 ? " dia" : " dias");
          }
          track.appendChild(marco);
          var rotX = r.barra ? x(r.fim) + esc.px + 6 : x(r.ini) + esc.px / 2 + 14;
          track.appendChild(h("span", { class: "ca-g-label" + (late ? " is-late" : ""), style: { left: rotX + "px" } }, late ? icone("alerta") : null, t.titulo));
          arrastarMarco(marco, t, r, esc.px);
        }
        row.appendChild(track);
        corpo.appendChild(row);
      });
    });
    scroller.appendChild(corpo);
    view.appendChild(scroller);

    function irHoje(inicial) {
      var sc = view.querySelector(".ca-gantt");
      if (!sc) return;
      var esquerda = view.querySelector(".ca-g-left");
      var visivel = sc.clientWidth - (esquerda ? esquerda.offsetWidth : 0);
      var xHoje = x(parseData(HOJE));
      if (inicial === true) {
        // Abre mostrando os atrasos em aberto até hoje, quando cabem na tela.
        var maisAntiga = null;
        lista.forEach(function (t) {
          var r = intervalo(t);
          if (r && !concluida(t) && (!maisAntiga || r.ini < maisAntiga)) maisAntiga = r.ini;
        });
        if (maisAntiga && xHoje - x(maisAntiga) < visivel - 60) {
          sc.scrollLeft = Math.max(0, x(maisAntiga) - 3 * esc.px);
          return;
        }
        sc.scrollLeft = Math.max(0, xHoje - visivel * 0.8);
        return;
      }
      sc.scrollLeft = Math.max(0, xHoje - visivel * 0.5);
    }
    function rolar(dir) {
      var sc = view.querySelector(".ca-gantt");
      if (sc) sc.scrollBy({ left: dir * (S.escala === "mes" ? 30 : 7) * esc.px, behavior: "smooth" });
    }
    if (S.entrouGantt) setTimeout(function () { irHoje(true); }, 0);
  }
  function arrastarMarco(el, t, r, px) {
    var inicioX = null;
    var delta = 0;
    var moveu = false;
    el.addEventListener("pointerdown", function (ev) {
      if (!t.pode_editar || ev.button !== 0) return;
      inicioX = ev.clientX;
      delta = 0;
      moveu = false;
      el.setPointerCapture(ev.pointerId);
    });
    el.addEventListener("pointermove", function (ev) {
      if (inicioX === null) return;
      var dx = ev.clientX - inicioX;
      if (Math.abs(dx) > 4) moveu = true;
      delta = Math.round(dx / px);
      el.style.transform = "translateX(" + delta * px + "px)" + (el.classList.contains("ca-g-marco") ? " rotate(45deg)" : "");
      if (moveu) el.dataset.tip = fmtData(isoDe(somarDias(r.fim, delta)));
    });
    el.addEventListener("pointerup", function () {
      if (inicioX === null) return;
      inicioX = null;
      if (!moveu) { abrirDrawer(t.id); return; }
      if (!delta) { render(); return; }
      var campos = {};
      if (r.barra) {
        campos.planejado_para = isoDe(somarDias(r.ini, delta));
        campos.data_vencimento = isoDe(somarDias(r.fim, delta));
      } else {
        var nova = isoDe(somarDias(r.fim, delta));
        if (t.vencimento) campos.data_vencimento = nova;
        if (!t.vencimento || t.planejado === t.vencimento) campos.planejado_para = nova;
      }
      salvarCampos(t.id, campos, "Entrega movida para " + fmtData(campos.data_vencimento || campos.planejado_para));
    });
    el.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); abrirDrawer(t.id); }
    });
  }

  // -------------------------------------------------------------- MIND MAP
  var MAPA = { x: 0, y: 0, z: 1, iniciado: false };
  var CORES_RAMOS = ["#FF7800", "#00B8D9", "#1090E0", "#7B68EE", "#2EA52C", "#D6409F", "#E5484D", "#AB6400"];
  function ramosMapa(lista) {
    var modo = S.mapaGrupo;
    var gs;
    if (modo === "status") gs = grupos(lista, "status");
    else if (modo === "pessoa") gs = grupos(lista, "pessoa");
    else gs = grupos(lista, "empresa");
    var corI = 0;
    gs.forEach(function (g) {
      if (modo === "empresa" && !g.empresa) g.cor = "#87909E";
      else if (modo === "pessoa") { /* cor da pessoa */ } else if (modo === "empresa") { g.cor = CORES_RAMOS[corI % CORES_RAMOS.length]; corI++; }
    });
    return gs;
  }
  function renderMapa(lista) {
    view.dataset.visao = "mapa";
    var gs = ramosMapa(lista);
    var NO_W = 240;
    var NO_H = 52;
    var GAP = 12;
    var RAMO_X = 280;
    var TAREFA_X = 560;
    var lados = [[], []];
    var alturas = [0, 0];
    gs.forEach(function (g) {
      var fechado = !!S.mapaFechados[S.mapaGrupo + ":" + g.chave];
      var n = fechado ? 1 : Math.max(1, g.itens.length);
      g._altura = n * (NO_H + GAP) + 28;
      g._fechado = fechado;
      var lado = alturas[0] <= alturas[1] ? 0 : 1;
      lados[lado].push(g);
      alturas[lado] += g._altura;
    });
    var nos = [];
    var arestas = [];
    nos.push({ tipo: "raiz", x: -110, y: -26, w: 220, h: 52 });
    lados.forEach(function (lst, lado) {
      var sinal = lado === 0 ? 1 : -1;
      var y = -alturas[lado] / 2;
      lst.forEach(function (g) {
        var cy = y + g._altura / 2;
        var gx = sinal > 0 ? RAMO_X - 100 : -RAMO_X - 100;
        nos.push({ tipo: "ramo", g: g, x: gx, y: cy - 20, w: 200, h: 40 });
        arestas.push({ x1: sinal * 110, y1: 0, x2: sinal > 0 ? gx : gx + 200, y2: cy, cor: g.cor });
        if (!g._fechado) {
          var ty = y + 14;
          g.itens.forEach(function (t) {
            var tx = sinal > 0 ? TAREFA_X - 40 : -TAREFA_X + 40 - NO_W;
            nos.push({ tipo: "tarefa", t: t, x: tx, y: ty, w: NO_W, h: NO_H, cor: g.cor });
            arestas.push({ x1: sinal > 0 ? gx + 200 : gx, y1: cy, x2: sinal > 0 ? tx : tx + NO_W, y2: ty + NO_H / 2, cor: g.cor });
            ty += NO_H + GAP;
          });
        }
        y += g._altura;
      });
    });
    var bbox = nos.reduce(function (b, n) {
      return { x1: Math.min(b.x1, n.x), y1: Math.min(b.y1, n.y), x2: Math.max(b.x2, n.x + n.w), y2: Math.max(b.y2, n.y + n.h) };
    }, { x1: 0, y1: 0, x2: 0, y2: 0 });

    var canvas = h("div", { class: "ca-map" });
    var mundo = h("div", { class: "ca-map-world" });
    var svgNS = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("class", "ca-map-edges");
    var pad = 40;
    svg.setAttribute("width", bbox.x2 - bbox.x1 + 2 * pad);
    svg.setAttribute("height", bbox.y2 - bbox.y1 + 2 * pad);
    svg.style.left = bbox.x1 - pad + "px";
    svg.style.top = bbox.y1 - pad + "px";
    arestas.forEach(function (a) {
      var p = document.createElementNS(svgNS, "path");
      var ox = bbox.x1 - pad;
      var oy = bbox.y1 - pad;
      var mx = (a.x1 + a.x2) / 2;
      p.setAttribute("d", "M" + (a.x1 - ox) + "," + (a.y1 - oy) + " C" + (mx - ox) + "," + (a.y1 - oy) + " " + (mx - ox) + "," + (a.y2 - oy) + " " + (a.x2 - ox) + "," + (a.y2 - oy));
      p.setAttribute("stroke", a.cor);
      svg.appendChild(p);
    });
    mundo.appendChild(svg);
    nos.forEach(function (n) {
      var el;
      var pos = { left: n.x + "px", top: n.y + "px", width: n.w + "px", height: n.h + "px" };
      if (n.tipo === "raiz") {
        el = h("div", { class: "ca-node is-root", style: pos }, icone("lista"), "Atividades Comerciais");
      } else if (n.tipo === "ramo") {
        var chave = S.mapaGrupo + ":" + n.g.chave;
        el = h("button", {
          type: "button",
          class: "ca-node is-branch",
          style: Object.assign({ "--c": n.g.cor }, pos),
          "aria-expanded": n.g._fechado ? "false" : "true",
          title: n.g._fechado ? "Mostrar tarefas" : "Recolher tarefas",
          onclick: function () { if (mapaArrastou) return; S.mapaFechados[chave] = !n.g._fechado; render(); },
        }, S.mapaGrupo === "pessoa" && n.g.pessoa ? avatar(n.g.pessoa, true) : null,
        h("span", { class: "ca-node-txt" }, n.g.label), h("span", { class: "ca-count" }, n.g.itens.length));
      } else {
        var t = n.t;
        el = h("button", {
          type: "button",
          class: "ca-node is-task" + (concluida(t) ? " is-done" : ""),
          style: Object.assign({ "--c": STATUS[t.status].cor }, pos),
          "aria-label": t.titulo,
          onclick: function () { if (!mapaArrastou) abrirDrawer(t.id); },
        }, circuloStatus(t), h("span", { class: "ca-node-txt" }, t.titulo), h("span", { class: "ca-node-meta" }, avatar(t.responsavel, true), bandeira(t.prioridade)),
        vencida(t) ? h("span", { class: "ca-node-late", "data-tip": "Venceu há " + atrasoDias(t) + " dias" }) : null);
      }
      mundo.appendChild(el);
    });
    canvas.appendChild(mundo);
    if (!nos.some(function (n) { return n.tipo === "tarefa"; }) && !gs.length) canvas.appendChild(h("div", { class: "ca-map-empty" }, vazio()));

    // Barra flutuante e minimapa
    var zoomTxt = h("span", { class: "ca-zoom-txt" });
    var barra = h("div", { class: "ca-map-bar" },
      h("button", { type: "button", class: "ca-icon-btn", "aria-label": "Diminuir zoom", onclick: function () { zoom(1 / 1.2); } }, icone("menos")),
      zoomTxt,
      h("button", { type: "button", class: "ca-icon-btn", "aria-label": "Aumentar zoom", onclick: function () { zoom(1.2); } }, icone("mais")),
      h("span", { class: "ca-map-sep" }),
      h("button", { type: "button", class: "ca-ghost is-sm", onclick: function () { ajustar(); } }, icone("ajustar"), "Ajustar à tela"),
      h("span", { class: "ca-map-sep" }),
      h("span", { class: "ca-map-lbl" }, "Ramos:"),
      h("div", { class: "ca-seg is-sm", role: "group", "aria-label": "Agrupar ramos por" }, [["empresa", "Empresa"], ["pessoa", "Responsável"], ["status", "Status"]].map(function (o) {
        return h("button", { type: "button", class: S.mapaGrupo === o[0] ? "is-on" : "", "aria-pressed": S.mapaGrupo === o[0] ? "true" : "false", onclick: function () { S.mapaGrupo = o[0]; MAPA.iniciado = false; render(); } }, o[1]);
      })));
    canvas.appendChild(barra);
    var mini = h("div", { class: "ca-minimap", "aria-hidden": "true" });
    var miniView = h("span", { class: "ca-mini-view" });
    var escMini = Math.min(160 / (bbox.x2 - bbox.x1 + 80), 100 / (bbox.y2 - bbox.y1 + 80));
    nos.forEach(function (n) {
      mini.appendChild(h("span", {
        class: "ca-mini-node",
        style: {
          left: (n.x - bbox.x1 + 40) * escMini + "px",
          top: (n.y - bbox.y1 + 40) * escMini + "px",
          width: Math.max(2, n.w * escMini) + "px",
          height: Math.max(2, n.h * escMini) + "px",
          background: n.tipo === "raiz" ? "#7B68EE" : n.tipo === "ramo" ? n.g.cor : "#C9CDD4",
        },
      }));
    });
    mini.appendChild(miniView);
    canvas.appendChild(mini);
    view.appendChild(canvas);

    function aplicar() {
      mundo.style.transform = "translate(" + MAPA.x + "px," + MAPA.y + "px) scale(" + MAPA.z + ")";
      canvas.style.backgroundSize = 20 * MAPA.z + "px " + 20 * MAPA.z + "px";
      canvas.style.backgroundPosition = MAPA.x + "px " + MAPA.y + "px";
      zoomTxt.textContent = Math.round(MAPA.z * 100) + "%";
      var vw = canvas.clientWidth / MAPA.z;
      var vh = canvas.clientHeight / MAPA.z;
      var vx = -MAPA.x / MAPA.z;
      var vy = -MAPA.y / MAPA.z;
      miniView.style.left = (vx - bbox.x1 + 40) * escMini + "px";
      miniView.style.top = (vy - bbox.y1 + 40) * escMini + "px";
      miniView.style.width = vw * escMini + "px";
      miniView.style.height = vh * escMini + "px";
    }
    function ajustar() {
      var w = canvas.clientWidth || 800;
      var hh = canvas.clientHeight || 500;
      var bw = bbox.x2 - bbox.x1 + 80;
      var bh = bbox.y2 - bbox.y1 + 80;
      MAPA.z = Math.max(0.25, Math.min(1.2, Math.min(w / bw, (hh - 60) / bh)));
      MAPA.x = w / 2 - ((bbox.x1 + bbox.x2) / 2) * MAPA.z;
      MAPA.y = (hh - 50) / 2 - ((bbox.y1 + bbox.y2) / 2) * MAPA.z;
      aplicar();
    }
    function zoom(f, cx, cy) {
      var w = canvas.clientWidth;
      var hh = canvas.clientHeight;
      cx = cx === undefined ? w / 2 : cx;
      cy = cy === undefined ? hh / 2 : cy;
      var nz = Math.max(0.2, Math.min(2.5, MAPA.z * f));
      MAPA.x = cx - (cx - MAPA.x) * (nz / MAPA.z);
      MAPA.y = cy - (cy - MAPA.y) * (nz / MAPA.z);
      MAPA.z = nz;
      aplicar();
    }
    canvas.addEventListener("wheel", function (ev) {
      ev.preventDefault();
      var r = canvas.getBoundingClientRect();
      if (ev.ctrlKey || ev.metaKey || (!ev.shiftKey && Math.abs(ev.deltaX) < 1)) {
        zoom(ev.deltaY < 0 ? 1.1 : 1 / 1.1, ev.clientX - r.left, ev.clientY - r.top);
      } else {
        MAPA.x -= ev.deltaX;
        MAPA.y -= ev.deltaY;
        aplicar();
      }
    }, { passive: false });
    var pan = null;
    var mapaArrastou = false;
    canvas.addEventListener("pointerdown", function (ev) {
      if (ev.target.closest(".ca-map-bar") || ev.button !== 0) return;
      pan = { x: ev.clientX, y: ev.clientY, ox: MAPA.x, oy: MAPA.y, id: ev.pointerId };
      mapaArrastou = false;
    });
    canvas.addEventListener("pointermove", function (ev) {
      if (!pan) return;
      var dx = ev.clientX - pan.x;
      var dy = ev.clientY - pan.y;
      if (!mapaArrastou && Math.abs(dx) + Math.abs(dy) > 4) {
        mapaArrastou = true;
        canvas.setPointerCapture(pan.id);
        canvas.classList.add("is-panning");
      }
      if (mapaArrastou) { MAPA.x = pan.ox + dx; MAPA.y = pan.oy + dy; aplicar(); }
    });
    function fimPan() {
      pan = null;
      canvas.classList.remove("is-panning");
      setTimeout(function () { mapaArrastou = false; }, 0);
    }
    canvas.addEventListener("pointerup", fimPan);
    canvas.addEventListener("pointercancel", fimPan);
    requestAnimationFrame(function () {
      if (!MAPA.iniciado) { MAPA.iniciado = true; ajustar(); } else aplicar();
    });
  }

  // ----------------------------------------------------------------- DRAWER
  var drawer = document.getElementById("caDrawer");
  var backdrop = document.getElementById("caBackdrop");
  var cacheDetalhe = {};
  function abrirDrawer(id, foco) {
    S.drawer = Number(id);
    S.drawerFoco = foco || "";
    drawer.hidden = false;
    backdrop.hidden = false;
    document.body.classList.add("ca-drawer-open");
    desenharDrawer();
    carregarDetalhe(S.drawer);
  }
  function fecharDrawer() {
    S.drawer = null;
    drawer.hidden = true;
    backdrop.hidden = true;
    document.body.classList.remove("ca-drawer-open");
  }
  backdrop.addEventListener("click", fecharDrawer);
  function carregarDetalhe(id) {
    fetch(URL_T.detalhe(id), { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        cacheDetalhe[id] = data;
        if (S.drawer === id) desenharAtividade();
      })
      .catch(function () { /* histórico é opcional */ });
  }
  function campo(rotulo, conteudo) {
    return h("div", { class: "ca-field" }, h("span", { class: "ca-field-lbl" }, rotulo), h("div", { class: "ca-field-val" }, conteudo));
  }
  function desenharDrawer() {
    var t = achar(S.drawer);
    if (!t) { fecharDrawer(); return; }
    var p = pai(t);
    var focoAtual = document.activeElement && drawer.contains(document.activeElement) ? document.activeElement.dataset.campo : null;
    drawer.innerHTML = "";
    var emp = EMPRESAS[t.empresa];
    drawer.appendChild(h("header", { class: "ca-dr-head" },
      h("p", { class: "ca-dr-crumb" }, "Atividades Comerciais", emp ? " / " + emp.nome : "", p ? " / " : "", p ? h("button", { type: "button", class: "ca-link", onclick: function () { abrirDrawer(p.id); } }, p.titulo) : null),
      h("div", { class: "ca-dr-actions" },
        t.pode_editar ? h("button", {
          type: "button", class: "ca-icon-btn", "data-tip": "Excluir", "aria-label": "Excluir tarefa",
          onclick: function (ev) {
            var b = ev.currentTarget;
            abrirMenu(b, [h("p", { class: "ca-menu-note" }, "Excluir esta tarefa" + ((t.subtarefas || []).length ? " e as subtarefas" : "") + "?"), itemMenu([icone("lixo"), "Excluir"], false, function () { excluir(t.id); }, "is-danger")], 220);
          },
        }, icone("lixo")) : null,
        h("button", { type: "button", class: "ca-icon-btn", "aria-label": "Fechar painel", onclick: fecharDrawer }, icone("x")))));

    var corpo = h("div", { class: "ca-dr-body" });
    var titulo = h("textarea", { class: "ca-dr-title", rows: "1", maxlength: "200", "aria-label": "Nome da tarefa", "data-campo": "titulo", disabled: !t.pode_editar });
    titulo.value = t.titulo;
    titulo.addEventListener("input", function () { autoAltura(titulo); });
    titulo.addEventListener("keydown", function (ev) { if (ev.key === "Enter") { ev.preventDefault(); titulo.blur(); } });
    titulo.addEventListener("blur", function () {
      var v = titulo.value.trim();
      if (v && v !== t.titulo) salvarCampos(t.id, { titulo: v });
      else titulo.value = t.titulo;
    });
    corpo.appendChild(titulo);

    var stBtn = h("button", { type: "button", class: "ca-dr-status", "aria-label": "Status", onclick: function () { menuStatus(stBtn, t); } }, pill(t.status), icone("setaBaixo"));
    var pessoasBtn = h("button", { type: "button", class: "ca-cell is-wide", "aria-label": "Responsáveis", onclick: function () { menuPessoas(pessoasBtn, t); } },
      avatares(t, 5), h("span", { class: "ca-muted" }, membros(t).map(function (id) { return PESSOAS[id] ? PESSOAS[id].nome.split(" ")[0] : ""; }).join(", ")));
    var entBtn = h("button", { type: "button", class: "ca-cell is-wide", "aria-label": "Data de entrega", onclick: function () { menuData(entBtn, t, "data_vencimento"); } },
      t.entrega ? dataEl(t, { icone: true }) : h("span", { class: "ca-muted" }, icone("calendario"), "Definir"),
      t.entrega && !t.vencimento ? h("span", { class: "ca-muted" }, "(dia do planner)") : null);
    if (vencida(t)) entBtn.appendChild(h("span", { class: "ca-late-txt" }, "Venceu há " + diasEntre(parseData(t.entrega), parseData(HOJE)) + " dias"));
    var planBtn = h("button", { type: "button", class: "ca-cell is-wide", "aria-label": "Dia no planner", onclick: function () { menuData(planBtn, t, "planejado_para"); } },
      t.planejado ? h("span", { class: "ca-date" }, icone("calendario"), fmtData(t.planejado)) : h("span", { class: "ca-muted" }, "Sem dia"),
      t.hora_inicio
        ? h("span", { class: "ca-hora is-static" }, icone("relogio"), t.hora_inicio + (t.hora_fim ? "–" + t.hora_fim : ""))
        : h("span", { class: "ca-link-txt" }, "definir horário"));
    var prBtn = h("button", { type: "button", class: "ca-cell is-wide", "aria-label": "Prioridade", onclick: function () { menuPrioridade(prBtn, t); } }, bandeira(t.prioridade), PRIO[t.prioridade].label);
    var empSel = h("select", { class: "ca-input", "aria-label": "Empresa", disabled: !t.pode_editar, onchange: function (ev) { salvarCampos(t.id, { empresa: ev.target.value }); } },
      h("option", { value: "" }, "Sem empresa"),
      D.empresas.map(function (e) { return h("option", { value: e.id, selected: e.id === t.empresa }, e.nome); }));

    corpo.appendChild(h("div", { class: "ca-dr-grid" },
      campo("Status", stBtn),
      campo("Responsáveis", pessoasBtn),
      campo("Data de entrega", entBtn),
      campo("Planner", planBtn),
      campo("Prioridade", prBtn),
      campo("Empresa", empSel),
      campo("Cronômetro", h("div", { class: "ca-dr-timer" }, timerBtn(t),
        (t.subtarefas || []).length ? h("span", { class: "ca-muted" }, "com subtarefas: ", h("strong", { "data-total": String(t.id) }, fmtCurto(tempoTotal(t)))) : null))));

    var desc = h("textarea", { class: "ca-dr-desc", rows: "4", placeholder: t.pode_editar ? "Adicione uma descrição" : "Sem descrição", "aria-label": "Descrição", "data-campo": "descricao", disabled: !t.pode_editar });
    desc.value = t.descricao || "";
    desc.addEventListener("blur", function () {
      if (desc.value.trim() !== (t.descricao || "").trim()) salvarCampos(t.id, { descricao: desc.value }, "Descrição salva");
    });
    corpo.appendChild(h("section", { class: "ca-dr-sec" }, h("h3", null, "Descrição"), desc));

    if (!t.pai) {
      var subs = t.subtarefas || [];
      var lista = h("ul", { class: "ca-dr-subs" });
      subs.forEach(function (s) {
        var cb = h("input", { type: "checkbox", checked: concluida(s), disabled: !s.pode_status, "aria-label": "Concluir " + s.titulo });
        cb.addEventListener("change", function () { mudarStatus(s.id, cb.checked ? "realizado" : "nao_iniciado"); });
        lista.appendChild(h("li", { class: concluida(s) ? "is-done" : "" }, cb,
          h("button", { type: "button", class: "ca-link", onclick: function () { abrirDrawer(s.id); } }, s.titulo),
          avatar(s.responsavel, true), s.entrega ? dataEl(s) : null));
      });
      if (!subs.length) lista.appendChild(h("li", { class: "ca-muted" }, "Nenhuma subtarefa."));
      var subSec = h("section", { class: "ca-dr-sec" }, h("h3", null, "Subtarefas", subs.length ? h("span", { class: "ca-count" }, subs.filter(concluida).length + "/" + subs.length) : null), lista);
      if (t.pode_editar) {
        var subInput = h("input", { type: "text", class: "ca-input", placeholder: "Nova subtarefa e Enter", maxlength: "200", "aria-label": "Nova subtarefa", "data-campo": "sub" });
        subInput.addEventListener("keydown", function (ev) {
          if (ev.key !== "Enter") return;
          ev.preventDefault();
          var v = subInput.value.trim();
          if (!v) return;
          subInput.disabled = true;
          post(URL_T.sub(t.id), { titulo: v, responsavel: t.responsavel }).then(function (data) {
            if (data.pai) substituir(data.pai);
            S.drawerFoco = "sub";
            render();
            desenharDrawer();
          }).catch(function (err) { subInput.disabled = false; toast(err.message); });
        });
        subSec.appendChild(subInput);
      }
      corpo.appendChild(subSec);
    }

    corpo.appendChild(h("section", { class: "ca-dr-sec", id: "caTempoSec", "data-campo-sec": "tempo" },
      h("div", { class: "ca-dr-sec-head" },
        h("h3", null, "Tempo gasto", h("span", { class: "ca-dr-total", "data-total": String(t.id) }, fmtCurto(tempoTotal(t)))),
        h("button", { type: "button", class: "ca-ghost is-sm", "data-campo": "lancar", onclick: function () { S.formTempo = t.id; S.editReg = null; desenharTempo(); var d = drawer.querySelector('[data-campo="tempo"]'); if (d) d.focus(); } }, icone("relogioMais"), "Lançar tempo")),
      h("p", { class: "ca-dr-hint" }, "Cada pessoa liga o próprio cronômetro; o total soma todos. Esqueceu de ligar? Lance o tempo à mão."),
      h("div", { class: "ca-tempo-box" }, h("p", { class: "ca-muted" }, "Carregando…"))));
    var ativ = h("section", { class: "ca-dr-sec ca-dr-activity", id: "caAtividade" }, h("h3", null, "Comentários e atividade"), h("ol", { class: "ca-feed" }, h("li", { class: "ca-muted" }, "Carregando…")));
    corpo.appendChild(ativ);
    drawer.appendChild(corpo);

    var comentario = h("textarea", { class: "ca-input", rows: "2", placeholder: "Escreva um comentário", "aria-label": "Comentário", "data-campo": "comentario" });
    var enviar = h("button", { type: "button", class: "ca-primary is-sm", onclick: function () {
      var v = comentario.value.trim();
      if (!v) return;
      enviar.disabled = true;
      post(URL_T.comentar(t.id), { texto: v }).then(function () {
        comentario.value = "";
        enviar.disabled = false;
        carregarDetalhe(t.id);
      }).catch(function (err) { enviar.disabled = false; toast(err.message); });
    } }, "Comentar");
    comentario.addEventListener("keydown", function (ev) { if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) enviar.click(); });
    drawer.appendChild(h("footer", { class: "ca-dr-foot" }, comentario, enviar));

    autoAltura(titulo);
    if (cacheDetalhe[t.id]) desenharAtividade();
    if (S.drawerFoco === "tempo") {
      var sec = drawer.querySelector("#caTempoSec");
      if (sec) sec.scrollIntoView({ block: "start" });
    }
    var foco = S.drawerFoco || focoAtual;
    S.drawerFoco = "";
    var alvo = foco ? drawer.querySelector('[data-campo="' + foco + '"]') : null;
    if (alvo) alvo.focus();
    else if (!drawer.contains(document.activeElement)) drawer.querySelector(".ca-dr-head .ca-icon-btn:last-child").focus({ preventScroll: true });
  }
  function autoAltura(el) { el.style.height = "auto"; el.style.height = el.scrollHeight + "px"; }
  function desenharAtividade() {
    var data = cacheDetalhe[S.drawer];
    var feed = drawer.querySelector(".ca-feed");
    if (!feed || !data) return;
    feed.innerHTML = "";
    (data.eventos || []).slice().reverse().forEach(function (ev) {
      var ehComentario = ev.tipo === "comentario";
      feed.appendChild(h("li", { class: ehComentario ? "is-comment" : "" },
        h("p", { class: "ca-feed-meta" }, h("strong", null, ev.autor), " · " + ev.quando + (ehComentario ? "" : " · " + ev.tipo_label)),
        h("p", { class: "ca-feed-txt" }, ev.texto || ev.tipo_label)));
    });
    if (!feed.children.length) feed.appendChild(h("li", { class: "ca-muted" }, "Sem registros ainda."));
    desenharTempo();
  }
  function fmtDia(iso) {
    if (iso === HOJE) return "Hoje";
    if (iso === isoDe(somarDias(parseData(HOJE), -1))) return "Ontem";
    return fmtData(iso);
  }
  function desenharTempo() {
    var data = cacheDetalhe[S.drawer];
    var box = drawer.querySelector(".ca-tempo-box");
    var t = achar(S.drawer);
    if (!box || !data || !t) return;
    var foco = document.activeElement && box.contains(document.activeElement) ? document.activeElement.dataset.campo : null;
    box.innerHTML = "";

    if (S.formTempo === t.id) {
      box.appendChild(formTempo(t, data, null));
      if (S.focarTempo) {
        S.focarTempo = false;
        foco = "tempo";
        drawer.querySelector("#caTempoSec").scrollIntoView({ block: "start" });
      }
    }

    var pessoas = data.tempo_por_pessoa || [];
    var max = pessoas.reduce(function (m, p) { return Math.max(m, p.segundos); }, 0) || 1;
    var ul = h("ul", { class: "ca-tempo-pessoas" });
    pessoas.forEach(function (p) {
      ul.appendChild(h("li", null,
        avatar(p.id, true) || h("span", { class: "ca-av is-sm is-off" }),
        h("span", { class: "ca-tp-nome" }, p.nome),
        h("span", { class: "ca-tp-barra" }, h("i", { style: { width: Math.max(4, Math.round((p.segundos / max) * 100)) + "%" } })),
        h("span", { class: "ca-tp-val" + (p.rodando ? " is-running" : "") }, fmtCurto(p.segundos), p.rodando ? " · rodando" : "")));
    });
    if (pessoas.length) box.appendChild(ul);
    else if (S.formTempo !== t.id) box.appendChild(h("p", { class: "ca-tempo-vazio" }, "Ninguém registrou tempo ainda. Ligue o cronômetro ou use “Lançar tempo”."));

    var regs = data.registros || [];
    if (regs.length) {
      var lista = h("ul", { class: "ca-regs" });
      regs.forEach(function (r) {
        if (S.editReg === r.id) { lista.appendChild(h("li", { class: "is-editing" }, formTempo(t, data, r))); return; }
        lista.appendChild(h("li", null,
          h("span", { class: "ca-reg-dia" }, fmtDia(r.data)),
          avatar(r.funcionario, true),
          h("span", { class: "ca-reg-nome" }, r.nome.split(" ")[0]),
          r.manual ? h("span", { class: "ca-tag" }, "manual") : null,
          r.rodando ? h("span", { class: "ca-tag is-live" }, "rodando") : null,
          h("strong", { class: "ca-reg-val" }, fmtCurto(r.segundos)),
          h("span", { class: "ca-reg-acoes" },
            r.pode_editar ? h("button", { type: "button", class: "ca-icon-btn", "aria-label": "Corrigir este tempo", "data-tip": "Corrigir", onclick: function () { S.editReg = r.id; S.formTempo = null; desenharTempo(); var i = box.querySelector('[data-campo="tempo"]'); if (i) { i.focus(); i.select(); } } }, icone("lapis")) : null,
            r.pode_editar ? h("button", { type: "button", class: "ca-icon-btn", "aria-label": "Remover este tempo", "data-tip": "Remover", onclick: function (ev) {
              var b = ev.currentTarget;
              abrirMenu(b, [h("p", { class: "ca-menu-note" }, "Remover " + fmtCurto(r.segundos) + " de " + r.nome.split(" ")[0] + "?"),
                itemMenu([icone("lixo"), "Remover tempo"], false, function () { salvarTempo(URL_T.tempoExcluir(r.id), {}, "Tempo removido"); }, "is-danger")], 220);
            } }, icone("lixo")) : null)));
      });
      box.appendChild(h("details", { class: "ca-regs-wrap", open: S.editReg ? true : null },
        h("summary", null, "Registros (" + regs.length + ")"), lista));
    }
    if (foco) { var alvo = box.querySelector('[data-campo="' + foco + '"]'); if (alvo) alvo.focus(); }
  }
  function formTempo(t, data, reg) {
    var duracao = h("input", { type: "text", class: "ca-input", "data-campo": "tempo", placeholder: "ex.: 1h30, 45min, 1:15", "aria-label": "Duração", value: reg ? fmtCurto(reg.segundos).replace("min", "min") : "" });
    var dia = h("input", { type: "date", class: "ca-input", "aria-label": "Dia", max: HOJE, value: reg ? reg.data : HOJE });
    var quem = null;
    if (!reg && data.pode_lancar_para_outros) {
      quem = h("select", { class: "ca-input", "aria-label": "Pessoa" }, D.pessoas.filter(function (p) { return p.ativo; }).map(function (p) {
        return h("option", { value: p.id, selected: p.id === D.eu }, p.nome);
      }));
    }
    var salvar = h("button", { type: "submit", class: "ca-primary is-sm" }, reg ? "Salvar" : "Lançar");
    var form = h("form", { class: "ca-tempo-form" },
      h("div", { class: "ca-tempo-campos" },
        h("label", null, h("span", null, "Duração"), duracao),
        h("label", null, h("span", null, "Dia"), dia),
        quem ? h("label", null, h("span", null, "Pessoa"), quem) : null),
      h("div", { class: "ca-tempo-botoes" }, salvar,
        h("button", { type: "button", class: "ca-ghost is-sm", onclick: function () { S.formTempo = null; S.editReg = null; desenharTempo(); } }, "Cancelar")));
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var campos = { duracao: duracao.value, data: dia.value };
      if (quem) campos.funcionario = quem.value;
      salvar.disabled = true;
      salvarTempo(reg ? URL_T.tempoEditar(reg.id) : URL_T.tempoLancar(t.id), campos, reg ? "Tempo corrigido" : "Tempo lançado")
        .then(function (ok) { if (!ok) salvar.disabled = false; });
    });
    duracao.addEventListener("keydown", function (ev) { if (ev.key === "Escape") { ev.stopPropagation(); S.formTempo = null; S.editReg = null; desenharTempo(); } });
    return form;
  }
  function salvarTempo(url, campos, msg) {
    var id = S.drawer;
    return post(url, campos).then(function (data) {
      if (data.tarefa) substituir(data.tarefa);
      S.formTempo = null;
      S.editReg = null;
      render();
      if (S.drawer === id) desenharDrawer();
      carregarDetalhe(id);
      toast(msg);
      return true;
    }).catch(function (err) { toast(err.message); return false; });
  }

  // Cronômetro do topo do SGI foi usado: sincroniza a tela.
  document.addEventListener("sgi:timer", function () {
    recarregar().then(function () { if (S.drawer) { desenharDrawer(); carregarDetalhe(S.drawer); } });
  });

  // --------------------------------------------------------------- início
  salvarUrl();
  render();
})();
