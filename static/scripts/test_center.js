(() => {
    const quiz = document.getElementById("quiz");
    if (!quiz) return;

    const questions = JSON.parse(quiz.dataset.questions);
    const answers = new Map();
    const stage = document.getElementById("test-stage");
    const category = document.getElementById("question-category");
    const questionText = document.getElementById("question-text");
    const options = document.getElementById("answer-options");
    const counter = document.getElementById("question-counter");
    const progress = document.getElementById("question-progress");
    const previousButton = document.getElementById("previous-button");
    const nextButton = document.getElementById("next-button");
    const error = document.getElementById("test-error");
    let currentIndex = 0;
    let transitioning = false;

    function renderQuestion() {
        const question = questions[currentIndex];
        category.textContent = question.category || "QUESTION";
        questionText.textContent = question.question;
        counter.textContent = `${currentIndex + 1} / ${questions.length}`;
        progress.value = currentIndex + 1;
        previousButton.disabled = currentIndex === 0;
        nextButton.disabled = !answers.has(question.id);
        nextButton.textContent = currentIndex === questions.length - 1 ? "Finish test" : "Next";
        options.replaceChildren();

        Object.entries(question.choices).forEach(([letter, text]) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "tactile-button answer-button";
            button.setAttribute("aria-pressed", String(answers.get(question.id) === letter));
            button.classList.toggle("is-selected", answers.get(question.id) === letter);
            button.innerHTML = `<span class="answer-letter">${letter}</span><span class="answer-text"></span>`;
            button.querySelector(".answer-text").textContent = text;
            button.addEventListener("click", () => {
                answers.set(question.id, letter);
                error.hidden = true;
                renderQuestion();
                options.querySelector(".is-selected")?.focus();
            });
            options.append(button);
        });
    }

    function transitionToQuestion(nextIndex) {
        if (transitioning) return;
        transitioning = true;
        stage.classList.add("is-leaving");
        window.setTimeout(() => {
            currentIndex = nextIndex;
            renderQuestion();
            stage.classList.remove("is-leaving");
            stage.classList.add("is-entering");
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    stage.classList.remove("is-entering");
                    window.setTimeout(() => {
                        transitioning = false;
                    }, 220);
                });
            });
        }, 200);
    }

    async function submitTest() {
        nextButton.disabled = true;
        previousButton.disabled = true;
        nextButton.textContent = "Submitting…";
        error.hidden = true;

        try {
            const response = await fetch(quiz.dataset.submitUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(Object.fromEntries(answers)),
            });
            const result = await response.json();
            if (!response.ok || result.submitted !== true) {
                throw new Error(result.error || "Your test could not be submitted. Please try again.");
            }
            stage.innerHTML = `
                <section class="completion-panel">
                    <div class="completion-card">
                        <p class="test-kicker">FINAL ENGLISH TEST</p>
                        <h1>Test submitted</h1>
                        <p>Your report has been sent for review. Results are not displayed here.</p>
                        <a class="tactile-button primary-button" href="${quiz.dataset.centerUrl}">Return to test center</a>
                    </div>
                </section>`;
            document.querySelector(".test-controls").hidden = true;
            counter.textContent = "Complete";
            progress.value = questions.length;
        } catch (submissionError) {
            error.textContent = submissionError.message;
            error.hidden = false;
            nextButton.disabled = false;
            previousButton.disabled = false;
            nextButton.textContent = "Retry submission";
        }
    }

    previousButton.addEventListener("click", () => {
        if (currentIndex > 0) transitionToQuestion(currentIndex - 1);
    });

    nextButton.addEventListener("click", () => {
        if (!answers.has(questions[currentIndex].id)) {
            error.textContent = "Choose an answer before continuing.";
            error.hidden = false;
            return;
        }
        if (currentIndex === questions.length - 1) {
            submitTest();
        } else {
            transitionToQuestion(currentIndex + 1);
        }
    });

    renderQuestion();
})();
