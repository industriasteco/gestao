(() => {
  const form = document.querySelector('#order-entry-form');
  const products = JSON.parse(document.querySelector('#billing-products-data').textContent);
  let prices = JSON.parse(document.querySelector('#billing-prices-data').textContent);
  const number = value => Number(value).toLocaleString('pt-BR', {maximumFractionDigits: 6});
  const money = value => value.toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
  function refresh() {
    const company = form.elements.company.value, client = form.elements.client.value, day = form.elements.date.value;
    for (const row of form.querySelectorAll('.order-item')) {
      const output = row.querySelector('.billing-preview');
      const id = row.querySelector('[name$="-product"]').value, product = products[id];
      if (!product) { output.textContent = ''; continue; }
      const valid = prices.filter(p => p.product === id && p.start <= day && (!p.end || p.end >= day));
      const groups = [valid.filter(p => p.company === company && p.client === client), valid.filter(p => p.company === company && !p.client), valid.filter(p => p.company === product.company && !p.client)];
      const selected = groups.find(group => group.length);
      const condition = selected?.length === 1 ? selected[0] : null;
      const choice = row.querySelector('[name$="-billing_unit"]').value;
      const unit = choice === 'PRODUCT' ? product.unit : choice || condition?.unit || product.unit;
      const quantity = Number(row.querySelector('[name$="-quantity"]').value);
      let factor = 1;
      if (unit === 'KG' && product.unit.toUpperCase() !== 'KG') {
        const configured = condition && (condition.unit || product.unit) === unit ? Number(condition.factor) : 0;
        factor = configured > 0 ? configured : Number(product.weight_g) / 1000;
        if (product.unit.toUpperCase() !== 'UN' || !(factor > 0)) {
          output.textContent = 'Cadastre o fator de conversão do cliente ou o peso do produto para converter em kg.'; continue;
        }
        if (!Number.isInteger(quantity)) {
          output.textContent = 'Informe uma quantidade inteira de pães em unidades.'; continue;
        }
      }
      const negotiated = row.querySelector('[name$="-client_price"]')?.value;
      const amount = negotiated !== undefined && negotiated !== '' ? Number(negotiated) : condition ? Number(condition.amount) : null;
      const mismatch = !negotiated && condition && (condition.unit || product.unit) !== unit;
      let message = `${number(quantity)} ${product.unit} → ${number(quantity * factor)} ${unit} para faturar.`;
      if (factor !== 1) message += ` Fator: ${number(factor)} kg por unidade (${number(factor * 1000)} g).`;
      if (mismatch) message += ' Confira o preço: a condição cadastrada usa outra unidade de faturamento.';
      else if (amount !== null && amount > 0 && Number.isFinite(amount)) message += ` ${money(amount)}/${unit} · Total previsto: ${money(quantity * factor * amount)}.`;
      else message += ' Preço pendente de cadastro.';
      output.textContent = message;
    }
  }
  form.addEventListener('input', refresh);
  form.addEventListener('change', refresh);
  form.addEventListener('billing-item-added', refresh);
  form.addEventListener('billing-record-saved', event => {
    const record = event.detail;
    if (record.unit) products[record.id] = record;
    if (record.billing_prices) {
      const ids = new Set(record.billing_prices.map(p => p.id));
      prices = prices.filter(p => !ids.has(p.id)).concat(record.billing_prices);
    }
    refresh();
  });
  refresh();
})();
