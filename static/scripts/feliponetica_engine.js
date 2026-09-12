(() => {
	const forms = document.querySelectorAll('[data-feliponetica-form]');

	function renderOutput(result, originalText, output, dialect) {
		output.replaceChildren();
		output.classList.add('feliponetica-output-screen');
		output.dataset.dialect = dialect;

		const originalWords = originalText.trim().split(/\s+/);
		const phoneticWords = result.trim().split(/\s+/);
		const row = document.createElement('div');
		row.className = 'feliponetica-word-row';

		originalWords.forEach((originalWord, index) => {
			const phoneticWord = phoneticWords[index] || '';
			const cell = document.createElement('div');
			cell.className = 'feliponetica-word-cell';
			const widthUnits = Math.max(originalWord.length, phoneticWord.length);
			cell.style.setProperty('--word-width', `${Math.max(7, widthUnits * 0.72)}em`);

			const originalLine = document.createElement('span');
			originalLine.className = 'feliponetica-original-word';
			originalLine.textContent = originalWord;
			const phoneticLine = document.createElement('span');
			phoneticLine.className = 'feliponetica-phonetic-word';
			phoneticLine.textContent = phoneticWord;
			cell.append(originalLine, phoneticLine);
			row.appendChild(cell);
		});

		output.appendChild(row);
		output.hidden = false;
	}

	async function transcribe(form) {
		const input = form.querySelector('[name="transcript_text"]');
		const result = document.getElementById(form.dataset.resultTarget);
		const button = form.querySelector('button[type="submit"]');
		const text = input.value.trim();

		if (!text) {
			result.textContent = 'Enter English text first.';
			result.hidden = false;
			return;
		}

		button.disabled = true;
		result.textContent = 'Transcribing...';
		result.hidden = false;

		try {
			const response = await fetch('/api/feliponetica/transcribe-page', {
				method: 'POST',
				headers: {'Content-Type': 'application/json'},
				body: JSON.stringify({
					dialect: form.dataset.dialect,
					text
				})
			});
			const payload = await response.json();
			if (!response.ok) {
				throw new Error(payload.error || 'Transcription failed.');
			}
			renderOutput(payload.result, text, result, form.dataset.dialect);
		} catch (error) {
			result.textContent = error.message;
		} finally {
			button.disabled = false;
		}
	}

	forms.forEach((form) => {
		form.addEventListener('submit', (event) => {
			event.preventDefault();
			transcribe(form);
		});
	});
})();
