for (const block of document.querySelectorAll('[data-client-prices]')) {
  const prefix = block.dataset.prefix;
  const total = block.querySelector(`[name="${prefix}-TOTAL_FORMS"]`);
  const items = block.querySelector('[data-client-price-items]');
  const initialItems = Array.from(items.children, item => item.cloneNode(true));
  block.querySelector('[data-add-client-price]').addEventListener('click', () => {
    const index = Number(total.value);
    if (index >= 50) return;
    items.insertAdjacentHTML('beforeend', block.querySelector('[data-empty-client-price]').innerHTML.replaceAll('__prefix__', String(index)));
    const source = items.firstElementChild.querySelector('select');
    const select = items.lastElementChild.querySelector('select');
    select.replaceChildren(...Array.from(source.options, option => option.cloneNode(true)));
    select.value = '';
    total.value = index + 1;
    select.focus();
  });
  block.closest('form').addEventListener('reset', () => {
    items.replaceChildren(...initialItems.map(item => item.cloneNode(true)));
    total.value = block.dataset.initialCount;
  });
}
