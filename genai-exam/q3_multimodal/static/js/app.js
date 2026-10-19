/* =============================================================================
   Multimodal AI-Based Image Understanding System — front-end logic (Q.3)
   Plain JavaScript (no build step). Every control in the interface is wired here.

   Honesty rules implemented in the UI:
   * the offline banner is shown whenever the server reports Offline Demo Mode;
   * an uploaded image is validated locally (type/size/decode) AND on the server;
   * offline results are always labelled "illustrative sample data";
   * an offline analysis of a *different* image produces an explanatory error,
     never a borrowed sample description.
   ========================================================================== */
'use strict';

const CONFIG = window.APP_CONFIG || {};
const state = {
  file: null,            // File object actually sent to the server
  local: null,           // {name, width, height, size, type, digest, sampleKey, objectUrl}
  analysis: null,        // data returned by /api/analyze
  analysisId: null,
  evaluation: null,
  mode: 'auto',
  busy: false,
};

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
};

/* ------------------------------------------------------------------ utils -- */
function bytesToText(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function toast(message, kind) {
  const box = $('toast');
  box.textContent = message;
  box.className = `app-toast${kind === 'error' ? ' bg-danger' : ''}`;
  clearTimeout(box._timer);
  box._timer = setTimeout(() => box.classList.add('d-none'), 4200);
}

function setLoading(on, text) {
  state.busy = on;
  $('loadingBox').classList.toggle('d-none', !on);
  if (text) $('loadingText').textContent = text;
  $('analyzeBtn').disabled = on;
}

function showError(title, error, extra) {
  const box = $('validationBox');
  const wrap = el('div', 'alert alert-danger');
  const head = el('div', 'fw-semibold');
  head.innerHTML = '<i class="bi bi-exclamation-octagon-fill"></i> ';
  head.appendChild(document.createTextNode(' ' + title));
  wrap.appendChild(head);
  if (error && error.message) wrap.appendChild(el('div', 'mt-1', error.message));
  if (error && error.hint) wrap.appendChild(el('div', 'small mt-1 fst-italic', error.hint));
  if (error && Array.isArray(error.details)) {
    error.details.filter(Boolean).forEach((detail) => {
      if (String(detail).trim() !== String(error.message || '').trim()) {
        wrap.appendChild(el('div', 'error-detail mt-1', String(detail)));
      }
    });
  }
  if (error && error.code) wrap.appendChild(el('div', 'small text-secondary mt-1', `error code: ${error.code}`));
  if (extra) wrap.appendChild(el('div', 'small mt-2', extra));
  box.replaceChildren(wrap);
}

function clearError() {
  $('validationBox').replaceChildren();
}

/* ------------------------------------------------------------ api helper -- */
async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, options);
  } catch (networkError) {
    throw { code: 'network', message: 'The browser could not reach the Flask server. Is it still running?', details: [String(networkError)] };
  }
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    if (response.ok) return response;   // file download
    throw { code: 'unexpected_response', message: `The server replied with HTTP ${response.status} and a non-JSON body.` };
  }
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    throw payload.error || { code: 'http_' + response.status, message: 'The request failed.' };
  }
  return payload;
}

async function sha256Hex(buffer) {
  if (!window.crypto || !window.crypto.subtle) return '(not available in this browser)';
  const digest = await window.crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, '0')).join('');
}

/* -------------------------------------------------- local image handling -- */
function decodeImage(objectUrl) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight });
    img.onerror = () => reject(new Error('The selected file could not be decoded as an image.'));
    img.src = objectUrl;
  });
}

async function acceptFile(file, sampleKey = null) {
  clearError();
  const name = (file.name || '').toLowerCase();
  const allowedExtension = /\.(jpg|jpeg|png|webp)$/.test(name);
  const allowedType = !file.type || CONFIG.allowedTypes.includes(file.type);
  if (!allowedExtension && !allowedType) {
    showError('Unsupported file type', {
      code: 'unsupported_type',
      message: `"${file.name}" is not a supported image. Allowed types: JPG, JPEG, PNG, WEBP.`,
      hint: 'The server also decodes the file contents and rejects anything that is not a real image.',
    });
    return;
  }
  if (file.size === 0) {
    showError('Empty file', { code: 'empty_file', message: 'That file is 0 bytes, so there is nothing to analyse.' });
    return;
  }
  if (file.size > CONFIG.maxMb * 1024 * 1024) {
    showError('File too large', {
      code: 'file_too_large',
      message: `The file is ${bytesToText(file.size)}. The maximum allowed size is ${CONFIG.maxMb} MB.`,
      hint: 'Compress or resize the image and try again.',
    });
    return;
  }

  const objectUrl = URL.createObjectURL(file);
  let size;
  try {
    size = await decodeImage(objectUrl);
  } catch (decodeError) {
    URL.revokeObjectURL(objectUrl);
    showError('Corrupted or unsupported image', {
      code: 'corrupted_image',
      message: 'The browser could not decode this file as an image, so it will not be uploaded.',
      details: [String(decodeError)],
    });
    return;
  }

  let digest = '(not available in this browser)';
  try {
    digest = await sha256Hex(await file.arrayBuffer());
  } catch (ignored) { /* digest is only informational on the client */ }

  if (state.local && state.local.objectUrl) URL.revokeObjectURL(state.local.objectUrl);
  state.file = file;
  state.local = {
    name: file.name, width: size.width, height: size.height, size: file.size,
    type: file.type || 'unknown', digest, sampleKey, objectUrl,
  };

  $('previewImg').src = objectUrl;
  $('previewWrap').classList.remove('d-none');
  $('fileName').textContent = file.name + (sampleKey ? ' (bundled example image)' : '');
  $('fileDims').textContent = `${size.width} × ${size.height} px`;
  $('fileSize').textContent = bytesToText(file.size);
  $('fileType').textContent = file.type || 'detected from contents on the server';
  $('fileDigest').textContent = digest;
  $('replaceBtn').disabled = false;
  $('removeBtn').disabled = false;
  $('fileInput').value = '';
  toast(`${file.name} is ready. Press "Analyze Image" to continue.`);
}

function clearImage() {
  if (state.local && state.local.objectUrl) URL.revokeObjectURL(state.local.objectUrl);
  state.file = null;
  state.local = null;
  $('previewWrap').classList.add('d-none');
  $('previewImg').removeAttribute('src');
  $('replaceBtn').disabled = true;
  $('removeBtn').disabled = true;
  ['fileName', 'fileDims', 'fileSize', 'fileType', 'fileDigest'].forEach((id) => { $(id).textContent = '—'; });
}

async function loadSample(key) {
  const sample = (CONFIG.samples || []).find((item) => item.key === key);
  if (!sample) return;
  setLoading(true, `Loading the bundled example image "${sample.filename}"…`);
  try {
    const response = await fetch(sample.url, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const blob = await response.blob();
    const file = new File([blob], sample.filename, { type: blob.type || 'image/jpeg' });
    await acceptFile(file, key);
    document.getElementById('analysis').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) {
    showError('Could not load the bundled example image', {
      code: 'sample_load_failed', message: String(error), hint: 'Check that the Flask server is running and the images/ folder is present.',
    });
  } finally {
    setLoading(false);
  }
}

/* --------------------------------------------------------------- analyse -- */
async function analyze() {
  if (state.busy) return;
  if (!state.file) {
    showError('No image selected', {
      code: 'missing_input',
      message: 'Choose an image with the file picker, drop one on the drop zone, or click one of the three example images.',
    });
    return;
  }
  clearError();
  setLoading(true, 'Validating the image and requesting the analysis…');
  $('noResults').classList.add('d-none');

  const form = new FormData();
  form.append('image', state.file, state.file.name);
  form.append('mode', state.mode);
  if (state.local && state.local.sampleKey) form.append('demo_key', state.local.sampleKey);

  try {
    const payload = await api('/api/analyze', { method: 'POST', body: form });
    state.analysis = payload.data;
    state.analysisId = payload.data.analysis_id;
    state.evaluation = null;
    renderResults(payload.data);
    $('resultsContent').classList.remove('d-none');
    $('evalBtn').disabled = false;
    $('aiReviewBtn').disabled = !(payload.data.mode === 'live');
    $('evalFindings').replaceChildren();
    $('evalCounts').replaceChildren();
    $('evalIllustrative').classList.add('d-none');
    $('evalDisclaimer').textContent = '';
    $('aiReviewResult').replaceChildren();
    $('evalHint').textContent = payload.data.mode === 'offline'
      ? 'Offline analysis loaded. Run the evaluation to see the illustrative findings for this sample image.'
      : 'Live analysis loaded. Run the evaluation to apply the deterministic checks, and use the second-opinion review if a live model is configured.';
    if (payload.data.mode === 'offline' && payload.data.sample) {
      runEvaluation();           // offline samples have curated findings - show them straight away
    }
    toast(payload.message || 'Analysis completed.');
    document.getElementById('results').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) {
    if (error && error.code === 'unavailable') {
      showError('Live model access is required for this image', error, CONFIG.unsupportedMessage);
    } else {
      showError('Analysis failed', error);
    }
    if (error && error.http_status) {
      // keep the dashboard hidden: nothing was produced, so nothing is displayed
      $('noResults').classList.remove('d-none');
    }
  } finally {
    setLoading(false);
  }
}

function renderResults(data) {
  const analysis = data.analysis || {};
  const offline = data.mode === 'offline';

  $('badgeMode').textContent = data.mode_label;
  $('badgeMode').className = `badge ${offline ? 'text-bg-warning' : 'text-bg-success'}`;
  $('badgeProvider').textContent = data.provider || 'n/a';
  $('badgeModel').textContent = data.model || 'n/a';
  $('badgeLatency').textContent = `${data.latency_ms} ms`;
  const validationOk = data.validation && data.validation.valid;
  $('badgeValidation').textContent = validationOk ? 'Schema valid' : 'Schema invalid';
  $('badgeValidation').className = `badge ${validationOk ? 'text-bg-success' : 'text-bg-danger'}`;

  const notice = $('resultsNotice');
  notice.replaceChildren();
  if (offline) {
    const banner = el('div', 'alert alert-warning');
    banner.appendChild(el('div', 'fw-semibold', data.banner || CONFIG.offlineBanner));
    banner.appendChild(el('div', 'small mt-1', CONFIG.sampleDataNotice));
    if (data.sample) {
      banner.appendChild(el('div', 'small mt-1', `Sample: ${data.sample.title} — source: ${data.sample.source}`));
      banner.appendChild(el('div', 'small', `Licence: ${data.sample.licence}`));
    }
    notice.appendChild(banner);
  } else {
    const banner = el('div', 'alert alert-success');
    banner.appendChild(el('div', 'fw-semibold', `Live AI Mode — analysis produced by ${data.model} through the ${data.provider}.`));
    banner.appendChild(el('div', 'small mt-1',
      'A live model can still be wrong. Schema validation passed, which proves the JSON shape only; '
      + 'run the evaluation and review the findings before trusting the text.'));
    notice.appendChild(banner);
  }
  (data.notes || []).forEach((note) => notice.appendChild(el('div', 'small text-secondary', '• ' + note)));
  (data.warnings || []).forEach((warning) => notice.appendChild(el('div', 'small text-warning-emphasis', '⚠ ' + warning)));

  const image = data.image || {};
  $('resultImage').src = image.preview_url
    ? image.preview_url
    : (state.local && state.local.objectUrl) || '';
  $('resultImage').alt = `Analysed image: ${image.filename || 'upload'}`;
  const metaRows = [
    ['File name', image.filename],
    ['Dimensions', `${image.width} × ${image.height} px`],
    ['Size', bytesToText(image.bytes || 0)],
    ['Validated type', image.media_type],
    ['SHA-256', image.digest],
  ];
  $('resultImageMeta').replaceChildren(...metaRows.map(([key, value]) => {
    const tr = el('tr');
    tr.appendChild(el('th', null, key));
    const td = el('td');
    if (key === 'SHA-256') td.className = 'digest';
    td.textContent = value === undefined || value === null ? '—' : String(value);
    tr.appendChild(td);
    return tr;
  }));

  $('rDescription').textContent = analysis.detailed_description || '';
  $('rCaption').textContent = analysis.caption || '';
  $('rSummary').textContent = analysis.summary || '';

  const activities = analysis.activities || [];
  $('rActivities').replaceChildren(
    ...(activities.length ? activities.map((a) => el('li', null, a)) : [el('li', 'text-secondary', 'none reported (empty array)')]));

  const uncertainties = analysis.uncertainties || [];
  $('rUncertainties').replaceChildren(
    ...(uncertainties.length ? uncertainties.map((u) => el('li', null, u)) : [el('li', 'text-secondary', 'none reported')]));

  const objects = analysis.objects || [];
  $('rObjects').replaceChildren(...(objects.length ? objects.map((obj) => {
    const tr = el('tr');
    tr.appendChild(el('td', 'fw-semibold', obj.name));
    const attrCell = el('td');
    (obj.attributes || []).forEach((attr) => attrCell.appendChild(el('span', 'attr-tag', attr)));
    if (!(obj.attributes || []).length) attrCell.appendChild(el('span', 'text-secondary small', 'no attributes'));
    tr.appendChild(attrCell);
    tr.appendChild(el('td', null, obj.evidence));
    return tr;
  }) : [(() => { const tr = el('tr'); const td = el('td', 'text-secondary', 'no objects reported'); td.colSpan = 3; tr.appendChild(td); return tr; })()]));

  const sample = data.sample;
  const gtBox = $('rGroundTruthBox');
  const sampleBox = $('rSampleBox');
  if (sample && Array.isArray(sample.ground_truth) && sample.ground_truth.length) {
    gtBox.classList.remove('d-none');
    $('rGroundTruth').replaceChildren(...sample.ground_truth.map((item) => el('li', null, item)));
  } else {
    gtBox.classList.add('d-none');
    $('rGroundTruth').replaceChildren();
  }
  if (sample) {
    sampleBox.classList.remove('d-none');
    sampleBox.replaceChildren(
      el('div', 'fw-semibold', `Illustrative sample data for "${sample.title}"`),
      el('div', 'mt-1', CONFIG.sampleDataNotice),
      el('div', 'mt-1', `The analysis text is hand-written demonstration data. Source: ${sample.source}`),
    );
  } else {
    sampleBox.classList.add('d-none');
  }

  $('jsonView').textContent = JSON.stringify(analysis, null, 2);
  renderValidation(data.validation || {});
}

function renderValidation(validation) {
  const box = $('validationStatus');
  box.replaceChildren();
  const ok = validation.valid;
  const head = el('div', `alert ${ok ? 'alert-success' : 'alert-danger'} mb-2`);
  head.appendChild(el('div', 'fw-semibold', ok ? '✔ Valid — the JSON matches the required schema.' : '✖ Invalid JSON structure.'));
  head.appendChild(el('div', 'small mt-1', validation.note || ''));
  box.appendChild(head);

  const list = el('ul', 'small mb-2');
  list.appendChild(el('li', null, `Required fields present: ${ok ? 'yes' : 'no'}`));
  list.appendChild(el('li', null, `Errors: ${validation.error_count || 0}`));
  (validation.errors || []).forEach((error) => list.appendChild(el('li', 'text-danger', `${error.field}: ${error.message}`)));
  list.appendChild(el('li', null, `Warnings: ${validation.warning_count || 0}`));
  (validation.warnings || []).forEach((warning) => list.appendChild(el('li', 'text-warning-emphasis', warning)));
  box.appendChild(list);

  const rules = el('div', 'small text-secondary');
  rules.textContent = 'Checked rules: ' + (validation.checked_rules || []).join(', ');
  box.appendChild(rules);
  box.appendChild(el('div', 'small mt-2',
    'Reminder: a valid schema does not mean the description is true. Structural validation and factual evaluation are separate stages.'));
}

/* ------------------------------------------------------------ evaluation -- */
async function runEvaluation(useSecondOpinion = false) {
  if (!state.analysisId) {
    $('evalHint').textContent = 'Analyse an image first — the evaluation compares an analysis with its image.';
    return;
  }
  if (useSecondOpinion) {
    $('aiReviewResult').replaceChildren(el('div', 'alert alert-info small', 'Asking the live model for a second opinion…'));
  }
  $('evalBtn').disabled = true;
  try {
    const payload = await api('/api/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ analysis_id: state.analysisId, use_second_opinion: !!useSecondOpinion }),
    });
    state.evaluation = payload.data.evaluation;
    renderEvaluation(payload.data);
    toast('Evaluation completed.');
  } catch (error) {
    if (useSecondOpinion) {
      const box = el('div', 'alert alert-danger small');
      box.appendChild(el('div', 'fw-semibold', 'The second-opinion review failed.'));
      box.appendChild(el('div', null, error.message || ''));
      if (error.hint) box.appendChild(el('div', 'fst-italic', error.hint));
      $('aiReviewResult').replaceChildren(box);
    } else {
      showError('Evaluation failed', error);
    }
  } finally {
    $('evalBtn').disabled = false;
  }
}

function renderEvaluation(data) {
  const evaluation = data.evaluation || {};
  const illustrative = $('evalIllustrative');
  if (evaluation.illustrative) {
    illustrative.classList.remove('d-none');
    illustrative.innerHTML = '<strong>Illustrative example.</strong> ' + CONFIG.sampleDataNotice +
      ' These findings come from comparing the hand-written sample analysis with the actual sample image.';
  } else {
    illustrative.classList.add('d-none');
  }

  const counts = evaluation.counts_labelled || {};
  const pills = Object.keys(counts).map((label) => {
    const key = (CONFIG.categories.find((c) => c.label === label) || {}).key || '';
    const pill = el('span', `count-pill category-${key}`);
    pill.appendChild(el('b', null, String(counts[label])));
    pill.appendChild(document.createTextNode(' ' + label));
    return pill;
  });
  const statusPills = [
    ['Confirmed', evaluation.confirmed], ['Rejected', evaluation.rejected],
    ['Edited', evaluation.edited], ['Pending review', evaluation.pending],
  ].map(([label, value]) => {
    const pill = el('span', 'count-pill');
    pill.appendChild(el('b', null, String(value || 0)));
    pill.appendChild(document.createTextNode(' ' + label));
    return pill;
  });
  $('evalCounts').replaceChildren(...pills, ...statusPills);
  $('evalDisclaimer').textContent = `${evaluation.disclaimer || ''} ${evaluation.how_produced || ''}`.trim();

  const container = $('evalFindings');
  container.replaceChildren();
  const findings = evaluation.findings || [];
  if (!findings.length) {
    container.appendChild(el('div', 'alert alert-success',
      'No problems were raised by the automatic checks for this analysis. That is not proof of correctness — '
      + 'it only means these heuristics found nothing to flag.'));
  }
  findings.forEach((finding, index) => container.appendChild(findingCard(finding, index + 1)));

  const second = evaluation.second_opinion;
  if (second) {
    const box = el('div', 'alert alert-info');
    box.appendChild(el('div', 'fw-semibold', `Second-opinion review — ${second.provider} / ${second.model}`));
    box.appendChild(el('div', 'small mt-1', second.label));
    const list = el('ul', 'small mb-0 mt-2');
    (second.concerns || []).forEach((concern) => {
      list.appendChild(el('li', null, `${concern.statement} (${concern.category}) — ${concern.explanation} Suggested correction: ${concern.suggested_correction}`));
    });
    if (!(second.concerns || []).length) list.appendChild(el('li', null, 'The reviewing model reported no concerns.'));
    box.appendChild(list);
    $('aiReviewResult').replaceChildren(box);
  }
}

function findingCard(finding, number) {
  const card = el('div', `finding cat-${finding.category} status-${finding.verification_status}`);
  card.dataset.findingId = finding.id;
  card.dataset.category = finding.category;

  const head = el('div', 'finding-head');
  head.appendChild(el('span', `badge text-bg-light category-${finding.category}`, `${number}. ${finding.category_label}`));
  const statusBadge = el('span', `badge ${finding.verification_status === 'confirmed' ? 'text-bg-success'
    : finding.verification_status === 'rejected' ? 'text-bg-secondary'
      : finding.verification_status === 'edited' ? 'text-bg-primary' : 'text-bg-warning'}`);
  statusBadge.textContent = finding.verification_label;
  head.appendChild(statusBadge);
  head.appendChild(el('span', 'badge text-bg-light', `source: ${finding.source}`));
  head.appendChild(el('span', 'badge text-bg-light', `confidence: ${finding.confidence}`));
  head.appendChild(el('span', 'finding-id ms-auto', finding.id));
  card.appendChild(head);

  const grid = el('dl', 'finding-grid');
  const rows = [
    ['Generated statement', finding.statement],
    ['What is actually visible', finding.visible],
    ['Why it is a problem', finding.why],
    ['Suggested correction', finding.suggested_correction || '—'],
    ['Verification status', finding.verification_label],
  ];
  rows.forEach(([label, value]) => {
    grid.appendChild(el('dt', null, label));
    grid.appendChild(el('dd', null, value));
  });
  card.appendChild(grid);

  if (finding.reviewer_note) card.appendChild(el('div', 'reviewer-note', 'Reviewer note: ' + finding.reviewer_note));

  const actions = el('div', 'finding-actions');
  actions.appendChild(actionButton('confirm', finding, 'Confirm finding', 'bi-check2-circle', 'btn-success'));
  actions.appendChild(actionButton('reject', finding, 'Reject finding', 'bi-x-circle', 'btn-outline-secondary'));
  actions.appendChild(actionButton('edit', finding, 'Edit finding', 'bi-pencil-square', 'btn-outline-primary'));
  actions.appendChild(actionButton('reset', finding, 'Reset to pending', 'bi-arrow-counterclockwise', 'btn-outline-secondary'));
  card.appendChild(actions);

  return card;
}

function actionButton(action, finding, label, icon, style) {
  const button = el('button', `btn btn-sm ${style}`);
  button.type = 'button';
  button.dataset.action = action;
  button.dataset.findingId = finding.id;
  const i = el('i', `bi ${icon}`);
  button.appendChild(i);
  button.appendChild(document.createTextNode(' ' + label));
  return button;
}

async function postReview(action) {
  try {
    const payload = await api('/api/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ analysis_id: state.analysisId, action }),
    });
    state.evaluation = payload.data.evaluation;
    renderEvaluation({ evaluation: payload.data.evaluation, mode: state.analysis.mode });
    toast(`Review action "${action.type}" recorded.`);
  } catch (error) {
    showError('Could not record the review action', error);
  }
}

function openEditor(card, finding) {
  if (card.querySelector('.finding-editor')) return;
  const editor = el('div', 'finding-editor');
  const fields = [
    ['statement', 'Generated statement', 'text'],
    ['visible', 'What is actually visible', 'text'],
    ['why', 'Why it is a problem', 'text'],
    ['suggested_correction', 'Suggested correction', 'text'],
  ];
  const inputs = {};
  fields.forEach(([key, label]) => {
    const wrap = el('div', 'mb-2');
    const id = `edit-${finding.id}-${key}`;
    const labelEl = el('label', 'form-label small fw-semibold mb-1', label);
    labelEl.htmlFor = id;
    const input = el('input', 'form-control form-control-sm');
    input.id = id;
    input.value = finding[key] || '';
    wrap.appendChild(labelEl);
    wrap.appendChild(input);
    editor.appendChild(wrap);
    inputs[key] = input;
  });

  const categoryWrap = el('div', 'mb-2');
  const categoryLabel = el('label', 'form-label small fw-semibold mb-1', 'Category');
  const categorySelect = el('select', 'form-select form-select-sm');
  (CONFIG.categories || []).forEach((category) => {
    const option = el('option', null, category.label);
    option.value = category.key;
    if (category.key === finding.category) option.selected = true;
    categorySelect.appendChild(option);
  });
  categoryWrap.appendChild(categoryLabel);
  categoryWrap.appendChild(categorySelect);
  editor.appendChild(categoryWrap);

  const noteWrap = el('div', 'mb-2');
  const noteLabel = el('label', 'form-label small fw-semibold mb-1', 'Reviewer note (optional)');
  const noteInput = el('input', 'form-control form-control-sm');
  noteInput.value = finding.reviewer_note || '';
  noteWrap.appendChild(noteLabel);
  noteWrap.appendChild(noteInput);
  editor.appendChild(noteWrap);

  const actions = el('div', 'd-flex gap-2');
  const save = el('button', 'btn btn-sm btn-primary');
  save.type = 'button';
  save.innerHTML = '<i class="bi bi-save"></i> Save changes';
  save.addEventListener('click', () => {
    postReview({
      type: 'edit',
      finding_id: finding.id,
      statement: inputs.statement.value,
      visible: inputs.visible.value,
      why: inputs.why.value,
      suggested_correction: inputs.suggested_correction.value,
      category: categorySelect.value,
      note: noteInput.value,
    });
  });
  const cancel = el('button', 'btn btn-sm btn-outline-secondary');
  cancel.type = 'button';
  cancel.textContent = 'Cancel';
  cancel.addEventListener('click', () => editor.remove());
  actions.appendChild(save);
  actions.appendChild(cancel);
  editor.appendChild(actions);
  card.appendChild(editor);
  inputs.statement.focus();
}

/* ------------------------------------------------------------- downloads -- */
function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

function downloadJson() {
  if (!state.analysis) return;
  const document_ = {
    image: state.analysis.image,
    execution: {
      mode: state.analysis.mode, mode_label: state.analysis.mode_label,
      provider: state.analysis.provider, model: state.analysis.model,
      latency_ms: state.analysis.latency_ms, illustrative: state.analysis.illustrative,
      started_at: state.analysis.started_at, finished_at: state.analysis.finished_at,
    },
    analysis: state.analysis.analysis,
    schema_validation: state.analysis.validation,
    prompt_used: state.analysis.prompt_used,
  };
  downloadBlob(new Blob([JSON.stringify(document_, null, 2)], { type: 'application/json' }),
    `analysis_${state.analysisId || 'result'}.json`);
  toast('JSON analysis downloaded.');
}

async function downloadReport(format) {
  if (!state.analysisId) return;
  try {
    const response = await api('/api/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ analysis_id: state.analysisId, format }),
    });
    const blob = await response.blob();
    downloadBlob(blob, `image_understanding_report_${String(state.analysisId).replace(':', '_')}.${format === 'json' ? 'json' : 'md'}`);
    toast(`Evaluation report downloaded (${format.toUpperCase()}).`);
  } catch (error) {
    showError('Report download failed', error);
  }
}

/* ---------------------------------------------------------------- wiring -- */
function wireEvents() {
  const dropZone = $('dropZone');
  const fileInput = $('fileInput');

  const openPicker = () => fileInput.click();
  $('browseBtn').addEventListener('click', openPicker);
  $('replaceBtn').addEventListener('click', openPicker);
  dropZone.addEventListener('click', (event) => {
    if (event.target.closest('button')) return;
    openPicker();
  });
  dropZone.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openPicker(); }
  });
  fileInput.addEventListener('change', () => {
    if (fileInput.files && fileInput.files[0]) acceptFile(fileInput.files[0]);
  });

  ['dragenter', 'dragover'].forEach((type) => dropZone.addEventListener(type, (event) => {
    event.preventDefault();
    event.stopPropagation();
    dropZone.classList.add('dragover');
  }));
  ['dragleave', 'drop'].forEach((type) => dropZone.addEventListener(type, (event) => {
    event.preventDefault();
    event.stopPropagation();
    dropZone.classList.remove('dragover');
  }));
  dropZone.addEventListener('drop', (event) => {
    const files = event.dataTransfer && event.dataTransfer.files;
    if (files && files.length) acceptFile(files[0]);
  });
  window.addEventListener('dragover', (event) => event.preventDefault());
  window.addEventListener('drop', (event) => event.preventDefault());

  $('removeBtn').addEventListener('click', () => {
    clearImage();
    clearError();
    $('resultsContent').classList.add('d-none');
    $('noResults').classList.remove('d-none');
    $('evalBtn').disabled = true;
    $('aiReviewBtn').disabled = true;
    toast('Image removed. Nothing was stored on the server.');
  });

  $('analyzeBtn').addEventListener('click', analyze);
  $('resetBtn').addEventListener('click', () => {
    clearImage();
    clearError();
    state.analysis = null;
    state.analysisId = null;
    state.evaluation = null;
    $('resultsContent').classList.add('d-none');
    $('noResults').classList.remove('d-none');
    $('evalFindings').replaceChildren();
    $('evalCounts').replaceChildren();
    $('evalIllustrative').classList.add('d-none');
    $('evalDisclaimer').textContent = '';
    $('aiReviewResult').replaceChildren();
    $('evalHint').textContent = 'Analyse an image first. The evaluation combines deterministic text checks with (for the three bundled examples) a manual comparison against a human ground-truth list.';
    $('evalBtn').disabled = true;
    $('aiReviewBtn').disabled = true;
    $('modeSelect').value = 'auto';
    state.mode = 'auto';
    updateModeHelp();
    toast('Interface reset.');
  });

  $('modeSelect').addEventListener('change', (event) => {
    state.mode = event.target.value;
    updateModeHelp();
  });

  $('sampleGallery').addEventListener('click', (event) => {
    const button = event.target.closest('[data-sample]');
    if (button) loadSample(button.dataset.sample);
  });

  document.querySelectorAll('.copy-btn').forEach((button) => {
    button.addEventListener('click', async () => {
      const target = $(button.dataset.copy);
      const text = target ? (target.value !== undefined && target.tagName === 'INPUT' ? target.value : target.innerText || target.textContent)
        : '';
      try {
        await navigator.clipboard.writeText(text || '');
        toast('Copied to the clipboard.');
      } catch (error) {
        // Fallback for browsers without the async clipboard API
        const area = document.createElement('textarea');
        area.value = text || '';
        document.body.appendChild(area);
        area.select();
        document.execCommand('copy');
        area.remove();
        toast('Copied to the clipboard.');
      }
    });
  });

  $('downloadJsonBtn').addEventListener('click', downloadJson);
  $('downloadReportBtn').addEventListener('click', () => downloadReport('md'));
  $('downloadReportJsonBtn').addEventListener('click', () => downloadReport('json'));

  $('evalBtn').addEventListener('click', () => runEvaluation(false));
  $('aiReviewBtn').addEventListener('click', () => {
    if (state.analysis && state.analysis.mode !== 'live') {
      $('aiReviewResult').replaceChildren(el('div', 'alert alert-warning small',
        'A second-opinion AI review needs a live model. Offline Demo Mode has no model to call, '
        + 'so this control stays disabled for offline results.'));
      return;
    }
    runEvaluation(true);
  });

  $('evalFindings').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-action]');
    if (!button || !state.evaluation) return;
    const finding = (state.evaluation.findings || []).find((item) => item.id === button.dataset.findingId);
    if (!finding) return;
    const action = button.dataset.action;
    if (action === 'edit') {
      openEditor(button.closest('.finding'), finding);
      return;
    }
    postReview({ type: action, finding_id: finding.id });
  });

  $('addFindingBtn').addEventListener('click', () => {
    if (!state.analysisId) {
      showError('Add finding', { code: 'no_analysis', message: 'Analyse an image before adding your own findings.' });
      return;
    }
    const statement = $('newStatement').value.trim();
    if (!statement) {
      showError('Add finding', { code: 'missing_input', message: 'The statement is required for a new finding.' });
      return;
    }
    postReview({
      type: 'add',
      finding: {
        statement,
        category: $('newCategory').value,
        visible: $('newVisible').value.trim(),
        why: $('newWhy').value.trim(),
        suggested_correction: $('newCorrection').value.trim(),
      },
    });
    ['newStatement', 'newVisible', 'newWhy', 'newCorrection'].forEach((id) => { $(id).value = ''; });
  });
}

function updateModeHelp() {
  const mode = $('modeSelect').value;
  const help = {
    auto: 'Automatic: uses a live model when an API key is configured, otherwise Offline Demo Mode.',
    offline: 'Offline Demo Mode: only the three bundled example images can be analysed, using clearly labelled illustrative sample data.',
    live: 'Live AI Mode: requires GEMINI_API_KEY or ANTHROPIC_API_KEY in the server environment. A failure is reported honestly — sample data is never substituted.',
  };
  $('modeHelp').textContent = help[mode] || '';
}

function renderBanner() {
  const banner = $('modeBanner');
  const offline = CONFIG.mode === 'offline';
  banner.className = `mode-banner${offline ? '' : ' live'}`;
  banner.innerHTML = offline
    ? `<i class="bi bi-wifi-off"></i>&nbsp; ${CONFIG.offlineBanner}`
    : `<i class="bi bi-cpu"></i>&nbsp; Live AI Mode — provider: <strong>${CONFIG.provider || 'n/a'}</strong>, model: <strong>${CONFIG.model}</strong>. Live results are not guaranteed correct and still need review.`;
  $('navModeBadge').innerHTML = offline
    ? '<span class="badge text-bg-warning">Offline Demo</span>'
    : '<span class="badge text-bg-success">Live AI</span>';
}

async function loadHealth() {
  try {
    const payload = await api('/api/health');
    const health = payload.data;
    $('healthMode').textContent = health.mode_label;
    $('healthMode').className = `stat-value ${health.mode === 'offline' ? 'text-warning-emphasis' : 'text-success'}`;
    $('healthProvider').textContent = health.provider || 'none (offline)';
    $('healthModel').textContent = health.model;
    $('healthLive').textContent = health.live_ready ? 'yes' : 'no (no API key)';
    $('healthReason').textContent = `${health.reason} · server: Python ${health.python} on ${health.platform} · samples: ${health.sample_images} · max upload: ${health.max_upload_mb} MB`;
  } catch (error) {
    $('healthReason').textContent = `Health check failed: ${error.message || error}`;
  }
}

function init() {
  renderBanner();
  wireEvents();
  updateModeHelp();
  $('modeSelect').value = 'auto';
  state.mode = 'auto';
  loadHealth();
}

document.addEventListener('DOMContentLoaded', init);
