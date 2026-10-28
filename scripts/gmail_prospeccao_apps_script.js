/**
 * Google Apps Script — e-mails no marcador Oportunidades/Quentes
 * com assunto "RSC: Agenda de final do ano CAPEX" → card no SGI.
 *
 * Propriedades do script:
 *   SGI_WEBHOOK_URL     = https://rsc-sgi.onrender.com/comercial/api/prospeccao-email/
 *   SGI_WEBHOOK_TOKEN   = (mesmo CRM_GMAIL_WEBHOOK_TOKEN do Render)
 *   SGI_ASSUNTO_GATILHO = RSC: Agenda de final do ano CAPEX
 *   SGI_GMAIL_LABEL     = Oportunidades/Quentes
 *
 * Rode instalarTriggerEnviado() uma vez.
 */

var ASSUNTO_PADRAO = 'RSC: Agenda de final do ano CAPEX';
var LABEL_PADRAO = 'Oportunidades/Quentes';

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
    .timeBased()
    .everyMinutes(5)
    .create();
  Logger.log('Trigger instalado: varre o marcador a cada 5 min.');
}

/**
 * Varre o marcador Oportunidades/Quentes + assunto gatilho e posta no SGI.
 */
function onGmailEnviadoProspeccao() {
  var assuntoGatilho = _prop('SGI_ASSUNTO_GATILHO', ASSUNTO_PADRAO);
  var label = _prop('SGI_GMAIL_LABEL', LABEL_PADRAO);
  var webhookUrl = _prop('SGI_WEBHOOK_URL', '');
  var token = _prop('SGI_WEBHOOK_TOKEN', '');
  if (!webhookUrl || !token) {
    Logger.log('Configure SGI_WEBHOOK_URL e SGI_WEBHOOK_TOKEN nas propriedades do script.');
    return;
  }

  var props = PropertiesService.getUserProperties();
  var processados = JSON.parse(props.getProperty('SGI_PROCESSED_IDS') || '{}');
  var agora = Date.now();
  var mudou = false;

  // Gmail: label aninhado → "Oportunidades/Quentes"
  var query =
    'label:' +
    label.replace(/"/g, '') +
    ' subject:"' +
    assuntoGatilho.replace(/"/g, '') +
    '"';

  Logger.log('Busca Gmail: ' + query);
  var threads = GmailApp.search(query, 0, 30);

  threads.forEach(function (thread) {
    thread.getMessages().forEach(function (msg) {
      var subject = (msg.getSubject() || '').trim();
      if (subject.toLowerCase() !== assuntoGatilho.toLowerCase()) return;

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
  } else {
    Logger.log('Nenhum e-mail novo no marcador com o assunto gatilho.');
  }
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

function testarUltimoEnviado() {
  onGmailEnviadoProspeccao();
}
