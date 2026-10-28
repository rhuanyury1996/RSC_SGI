/**
 * Google Apps Script — ao ENVIAR e-mail com assunto exato
 * "RSC: Agenda de final do ano CAPEX", cria card no SGI (RSC · Pré-vendas).
 *
 * Instalação (conta Workspace):
 * 1. https://script.google.com → Novo projeto
 * 2. Cole este arquivo no editor (Code.gs)
 * 3. Projeto → Configurações → propriedades do script:
 *      SGI_WEBHOOK_URL  = https://SEU-DOMINIO/comercial/api/prospeccao-email/
 *      SGI_WEBHOOK_TOKEN = (mesmo valor de CRM_GMAIL_WEBHOOK_TOKEN no Render)
 *      SGI_ASSUNTO_GATILHO = RSC: Agenda de final do ano CAPEX
 * 4. Executar uma vez a função instalarTriggerEnviado() e autorizar Gmail
 * 5. Envie um e-mail de teste com o assunto gatilho
 */

var ASSUNTO_PADRAO = 'RSC: Agenda de final do ano CAPEX';

function _prop(chave, fallback) {
  var v = PropertiesService.getScriptProperties().getProperty(chave);
  return (v && String(v).trim()) || (fallback || '');
}

function instalarTriggerEnviado() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'onGmailEnviadoProspeccao') {
      ScriptApp.deleteTrigger(t);
    }
  });
  ScriptApp.newTrigger('onGmailEnviadoProspeccao')
    .forUser()
    .timeBased()
    .everyMinutes(5)
    .create();
  // Marca a partir de agora para não reprocessar histórico antigo
  PropertiesService.getUserProperties().setProperty(
    'SGI_LAST_SENT_MS',
    String(Date.now())
  );
  Logger.log('Trigger instalado: varre e-mails enviados a cada 5 min.');
}

/**
 * Varre "Enviados" recentes e posta no SGI os que baterem o assunto gatilho.
 * (Gmail não tem trigger nativo "onSend"; polling curto é o caminho estável.)
 */
function onGmailEnviadoProspeccao() {
  var assuntoGatilho = _prop('SGI_ASSUNTO_GATILHO', ASSUNTO_PADRAO);
  var webhookUrl = _prop('SGI_WEBHOOK_URL', '');
  var token = _prop('SGI_WEBHOOK_TOKEN', '');
  if (!webhookUrl || !token) {
    Logger.log('Configure SGI_WEBHOOK_URL e SGI_WEBHOOK_TOKEN nas propriedades do script.');
    return;
  }

  var props = PropertiesService.getUserProperties();
  var lastMs = Number(props.getProperty('SGI_LAST_SENT_MS') || '0');
  var agora = Date.now();
  // Janela de segurança: últimos 15 minutos (ou desde a última execução)
  var desdeMs = Math.max(lastMs - 60 * 1000, agora - 15 * 60 * 1000);
  var desde = new Date(desdeMs);
  var query =
    'in:sent subject:"' +
    assuntoGatilho.replace(/"/g, '') +
    '" after:' +
    Utilities.formatDate(desde, Session.getScriptTimeZone(), 'yyyy/MM/dd');

  var threads = GmailApp.search(query, 0, 20);
  var processados = JSON.parse(props.getProperty('SGI_PROCESSED_IDS') || '{}');
  var mudou = false;
  var maxSent = lastMs;

  threads.forEach(function (thread) {
    thread.getMessages().forEach(function (msg) {
      var subject = (msg.getSubject() || '').trim();
      if (subject.toLowerCase() !== assuntoGatilho.toLowerCase()) return;

      var sentAt = msg.getDate().getTime();
      if (sentAt < desdeMs) return;
      if (sentAt > maxSent) maxSent = sentAt;

      var mid = msg.getId();
      if (processados[mid]) return;

      var toList = _parseAddresses(msg.getTo());
      var payload = {
        subject: subject,
        body: msg.getPlainBody() || '',
        from_email: _extractEmail(msg.getFrom()),
        from_name: _extractName(msg.getFrom()),
        to: toList,
        cc: _parseAddresses(msg.getCc()),
        message_id: mid,
        empresa: _guessEmpresa(msg.getPlainBody() || '', toList),
      };

      var resp = UrlFetchApp.fetch(webhookUrl, {
        method: 'post',
        contentType: 'application/json',
        headers: { 'X-SGI-Token': token },
        payload: JSON.stringify(payload),
        muteHttpExceptions: true,
      });
      Logger.log('SGI ' + mid + ' → ' + resp.getResponseCode() + ' ' + resp.getContentText());

      processados[mid] = agora;
      mudou = true;
    });
  });

  if (mudou) {
    // Mantém só os últimos ~200 ids
    var ids = Object.keys(processados);
    if (ids.length > 200) {
      ids
        .sort(function (a, b) {
          return processados[a] - processados[b];
        })
        .slice(0, ids.length - 200)
        .forEach(function (id) {
          delete processados[id];
        });
    }
    props.setProperty('SGI_PROCESSED_IDS', JSON.stringify(processados));
  }
  props.setProperty('SGI_LAST_SENT_MS', String(Math.max(maxSent, agora)));
}

function _extractEmail(fromHeader) {
  var m = String(fromHeader || '').match(/<([^>]+)>/);
  if (m) return m[1].trim().toLowerCase();
  return String(fromHeader || '')
    .trim()
    .toLowerCase();
}

function _extractName(fromHeader) {
  var s = String(fromHeader || '');
  var m = s.match(/^"?([^"<]+)"?\s*</);
  return m ? m[1].trim() : '';
}

function _parseAddresses(header) {
  if (!header) return [];
  return String(header)
    .split(',')
    .map(function (part) {
      part = part.trim();
      if (!part) return null;
      return {
        email: _extractEmail(part),
        name: _extractName(part),
      };
    })
    .filter(function (x) {
      return x && x.email;
    });
}

function _guessEmpresa(body, toList) {
  var patterns = [
    /nós e a\s+([A-ZÁÉÍÓÚÂÊÔÃÕÜ][\w\-]*(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÜ][\w\-]*){0,3})/i,
    /entre nós e a\s+([A-ZÁÉÍÓÚÂÊÔÃÕÜ][\w\-]*(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÜ][\w\-]*){0,3})/i,
    /com a\s+([A-ZÁÉÍÓÚÂÊÔÃÕÜ][\w\-]*(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÜ][\w\-]*){0,3})/i,
  ];
  for (var i = 0; i < patterns.length; i++) {
    var m = body.match(patterns[i]);
    if (m) return m[1].trim();
  }
  if (toList && toList[0] && toList[0].email) {
    var dom = toList[0].email.split('@')[1] || '';
    var base = (dom.split('.')[0] || '').toLowerCase();
    if (base && ['gmail', 'hotmail', 'outlook', 'yahoo'].indexOf(base) < 0) {
      return base.charAt(0).toUpperCase() + base.slice(1);
    }
  }
  return '';
}

/** Teste manual: usa o último enviado com o assunto gatilho. */
function testarUltimoEnviado() {
  onGmailEnviadoProspeccao();
}
