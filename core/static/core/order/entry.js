const orderForm = document.querySelector('#order-entry-form');
const companySelect = orderForm.querySelector('[name="company"]');
const statusMessage = document.querySelector('#quick-record-status');
const dialogs = {client: document.querySelector('#quick-client-dialog'), product: document.querySelector('#quick-product-dialog')};
let targetProduct = null;

function announce(message) {
  statusMessage.textContent = message;
  statusMessage.hidden = false;
}

orderForm.addEventListener('click', event => {
  const button = event.target.closest('[data-quick-open]');
  if (!button) return;
  if (!companySelect.value) {
    announce('Selecione a empresa do pedido antes de cadastrar o cliente ou produto.');
    companySelect.focus();
    return;
  }
  const kind = button.dataset.quickOpen;
  const dialog = dialogs[kind];
  if (!dialog) return;
  if (kind === 'product') targetProduct = button.closest('.order-item').querySelector('select');
  const form = dialog.querySelector('form');
  const company = form.elements.namedItem(`${dialog.dataset.prefix}-company`);
  company.value = companySelect.value;
  company.disabled = true;
  dialog.dataset.company = companySelect.value;
  if (!form.elements.request_key.value) form.elements.request_key.value = crypto.randomUUID();
  dialog.showModal();
  form.querySelector('input[type=text]').focus();
});

for (const [kind, dialog] of Object.entries(dialogs)) {
  if (!dialog) continue;
  const form = dialog.querySelector('form');
  const errors = dialog.querySelector('.quick-record-errors');
  dialog.querySelectorAll('[data-close-dialog]').forEach(button => button.addEventListener('click', () => dialog.close()));
  dialog.addEventListener('cancel', event => { if (form.dataset.saving) event.preventDefault(); });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (form.dataset.saving) return;
    errors.hidden = true;
    form.querySelectorAll('[aria-invalid]').forEach(field => field.removeAttribute('aria-invalid'));
    const data = new FormData(form);
    data.set(`${dialog.dataset.prefix}-company`, dialog.dataset.company);
    const buttons = dialog.querySelectorAll('button');
    buttons.forEach(button => { button.disabled = true; });
    form.dataset.saving = 'true';
    try {
      const response = await fetch(form.action, {method: 'POST', body: data, credentials: 'same-origin', headers: {'Accept': 'application/json'}});
      if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Não foi possível concluir. Confira sua conexão e se seu acesso continua ativo.');
      const result = await response.json();
      if (!response.ok) {
        if (response.status === 409) form.elements.request_key.value = crypto.randomUUID();
        const messages = [];
        for (const [name, issues] of Object.entries(result.errors || {})) {
          const field = form.elements.namedItem(`${dialog.dataset.prefix}-${name}`);
          if (field) field.setAttribute('aria-invalid', 'true');
          const label = field ? form.querySelector(`label[for="${field.id}"]`)?.textContent : '';
          for (const issue of issues) messages.push(`${label || ''} ${issue.message}`.trim());
        }
        throw new Error(messages.join('\n') || result.message || 'Confira os dados e tente novamente.');
      }
      const record = result.record;
      const selects = kind === 'client' ? [orderForm.querySelector('[name="client"]')] : orderForm.querySelectorAll('.order-item select');
      for (const select of selects) {
        if (!Array.from(select.options).some(option => option.value === record.id)) select.add(new Option(record.name, record.id));
      }
      const target = kind === 'client' ? selects[0] : targetProduct;
      target.value = record.id;
      target.dispatchEvent(new Event('change', {bubbles: true}));
      form.reset();
      form.elements.request_key.value = '';
      dialog.close();
      announce(`${record.name} cadastrado e selecionado no pedido.`);
      target.focus();
    } catch (error) {
      errors.textContent = error.message;
      errors.style.whiteSpace = 'pre-line';
      errors.hidden = false;
      errors.focus();
    } finally {
      delete form.dataset.saving;
      buttons.forEach(button => { button.disabled = false; });
    }
  });
}

document.querySelector('#add-order-item').addEventListener('click', () => {
  const total = document.querySelector('#id_form-TOTAL_FORMS');
  const index = Number(total.value);
  if (index >= 100) { announce('O pedido permite até 100 itens.'); return; }
  const container = document.querySelector('#order-items');
  container.insertAdjacentHTML('beforeend', document.querySelector('#empty-order-item').innerHTML.replaceAll('__prefix__', String(index)));
  const select = container.lastElementChild.querySelector('select');
  const source = container.firstElementChild.querySelector('select');
  select.replaceChildren(...Array.from(source.options, option => option.cloneNode(true)));
  select.value = '';
  total.value = index + 1;
  select.focus();
});
