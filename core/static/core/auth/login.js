const passwordInput = document.querySelector('#id_password');
const passwordToggle = document.querySelector('.password-toggle');

if (passwordInput && passwordToggle) {
  passwordToggle.hidden = false;
  passwordToggle.addEventListener('click', () => {
    const visible = passwordInput.type === 'password';
    passwordInput.type = visible ? 'text' : 'password';
    passwordToggle.textContent = visible ? 'Ocultar' : 'Mostrar';
    passwordToggle.setAttribute('aria-label', visible ? 'Ocultar senha' : 'Mostrar senha');
    passwordToggle.setAttribute('aria-pressed', String(visible));
  });
}
