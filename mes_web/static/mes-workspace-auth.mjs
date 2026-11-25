const form = document.querySelector('#workspace-entry');
const feedback = document.querySelector('#workspace-error');
const pairing = form.dataset.mode === 'pair';

form.innerHTML = pairing ? `
  <label>Eşleştirme kodu<input name="code" required minlength="12" maxlength="120" autocomplete="off" autocapitalize="none" spellcheck="false"></label>
  <button class="preset-button tablet-button">Tableti eşleştir</button>` : `
  <label>Kullanıcı adı<input name="username" required maxlength="40" autocomplete="username"></label>
  <label>Parola<input type="password" name="password" required maxlength="256" autocomplete="current-password"></label>
  <button class="preset-button tablet-button">Oturum aç</button>`;

form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = form.querySelector('button');
  button.disabled = true;
  feedback.textContent = '';
  try {
    const response = await fetch(`/api/workspace/${pairing ? 'pair' : 'login'}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Giriş bilgilerini kontrol edin.');
    const designer = !pairing && new URLSearchParams(location.search).get('alan') === 'designer';
    location.replace(designer ? '/atolye-onizleme' : result.path);
  } catch (error) {
    feedback.textContent = error.message;
    button.disabled = false;
  }
});
