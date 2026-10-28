(() => {
    const quiz = document.getElementById("quiz");
    if (!quiz) return;

    const questions = JSON.parse(quiz.dataset.questions);
    const sequence = JSON.parse(quiz.dataset.sequence || "[]");
    const answers = new Map();
    const lockedAnswers = new Set();
    const stage = document.getElementById("test-stage");
    const questionPanel = document.getElementById("question-panel");
    const sequencePanel = document.getElementById("sequence-panel");
    const panelImages = document.getElementById("panel-images");
    const category = document.getElementById("question-category");
    const questionText = document.getElementById("question-text");
    const questionImage = document.getElementById("question-image");
    const questionAudio = document.getElementById("question-audio");
    const options = document.getElementById("answer-options");
    const counter = document.getElementById("question-counter");
    const progress = document.getElementById("question-progress");
    const previousButton = document.getElementById("previous-button");
    const nextButton = document.getElementById("next-button");
    const error = document.getElementById("test-error");
    const mediaError = document.getElementById("media-error");
    const participantName = document.getElementById("participant-name");
    const controls = document.querySelector(".test-controls");
    const questionIndexes = new Map(
        questions.map((question, index) => [String(question.id), index])
    );
    const sequenceItems = sequence.length
        ? sequence
        : questions.map((question) => ({ type: "question", id: question.id }));
    let currentIndex = 0;
    let sequenceIndex = -1;
    let transitioning = false;
    let waitingForAudio = false;
    let awaitingSubmissionRetry = false;
    let activeAudioKey = null;
    let audioStatus = "idle";
    let audioPlayback = Promise.resolve();
    let cleanupAudioListeners = null;

    function startAudio(key, url, replayEnded = false) {
        if (!url) return Promise.resolve();
        if (activeAudioKey === key && audioStatus === "playing") {
            return audioPlayback;
        }
        if (activeAudioKey === key && audioStatus === "ended" && !replayEnded) {
            return Promise.resolve();
        }

        if (cleanupAudioListeners) cleanupAudioListeners();
        questionAudio.pause();
        questionAudio.removeAttribute("src");
        questionAudio.load();
        activeAudioKey = key;
        audioStatus = "playing";
        mediaError.hidden = true;

        let resolvePlayback;
        let rejectPlayback;
        audioPlayback = new Promise((resolve, reject) => {
            resolvePlayback = resolve;
            rejectPlayback = reject;
        });
        audioPlayback.catch(() => {});

        let settled = false;
        const cleanup = () => {
            questionAudio.removeEventListener("ended", onEnded);
            questionAudio.removeEventListener("error", onError);
            cleanupAudioListeners = null;
        };
        const onEnded = () => {
            if (settled || activeAudioKey !== key) return;
            settled = true;
            audioStatus = "ended";
            cleanup();
            resolvePlayback();
        };
        const onError = () => {
            if (settled || activeAudioKey !== key) return;
            settled = true;
            audioStatus = "failed";
            cleanup();
            mediaError.textContent = "Question audio could not be played. Press Next to retry.";
            mediaError.hidden = false;
            rejectPlayback(new Error(mediaError.textContent));
        };
        cleanupAudioListeners = cleanup;
        questionAudio.addEventListener("ended", onEnded);
        questionAudio.addEventListener("error", onError);
        questionAudio.src = url;
        if (questionAudio.readyState > 0) questionAudio.currentTime = 0;
        questionAudio.play().catch(onError);
        return audioPlayback;
    }

    function renderQuestion(questionIndex) {
        currentIndex = questionIndex;
        const question = questions[currentIndex];
        questionPanel.hidden = false;
        sequencePanel.hidden = true;
        options.hidden = false;
        controls.hidden = false;
        stage.classList.remove("is-panel");
        category.textContent = question.category || "QUESTION";
        questionText.textContent = question.question;
        questionImage.hidden = !question.image;
        questionImage.removeAttribute("src");
        if (question.image) {
            questionImage.src = question.image;
            questionImage.alt = question.question;
        }
        mediaError.hidden = true;
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
            button.disabled = lockedAnswers.has(question.id);
            button.innerHTML = `<span class="answer-letter">${letter}</span><span class="answer-text"></span>`;
            button.querySelector(".answer-text").textContent = text;
            button.addEventListener("click", () => {
                if (lockedAnswers.has(question.id)) return;
                answers.set(question.id, letter);
                error.hidden = true;
                options.querySelectorAll(".answer-button").forEach((choice) => {
                    const selected = choice === button;
                    choice.classList.toggle("is-selected", selected);
                    choice.setAttribute("aria-pressed", String(selected));
                });
                nextButton.disabled = false;
                if (question.audio && audioStatus === "failed") {
                    startAudio(`question:${question.id}`, question.audio).catch(() => {});
                }
            });
            options.append(button);
        });

        if (question.audio) {
            startAudio(`question:${question.id}`, question.audio, true).catch(() => {});
        }
    }

    function showPanel(panel) {
        questionPanel.hidden = true;
        sequencePanel.hidden = false;
        options.hidden = true;
        controls.hidden = true;
        stage.classList.add("is-panel");
        panelImages.replaceChildren();
        panel.images.forEach((imageUrl) => {
            const image = document.createElement("img");
            image.src = imageUrl;
            image.alt = "";
            panelImages.append(image);
        });
        counter.textContent = "Introduction";
        progress.value = currentIndex;
        mediaError.hidden = true;
        if (panel.audio) {
            startAudio(`panel:${sequenceIndex}`, panel.audio).catch(() => {});
        }
        window.setTimeout(() => {
            if (sequenceItems[sequenceIndex] === panel) {
                transitionToSequence(sequenceIndex + 1);
            }
        }, panel.duration * 1000);
    }

    function showSequenceItem(nextIndex) {
        sequenceIndex = nextIndex;
        if (sequenceIndex >= sequenceItems.length) {
            submitTest();
            return;
        }

        const item = sequenceItems[sequenceIndex];
        if (item.type === "panel") {
            showPanel(item);
            return;
        }

        const questionIndex = questionIndexes.get(String(item.id));
        if (questionIndex === undefined) {
            throw new Error(`Quiz sequence references missing question ${item.id}.`);
        }
        renderQuestion(questionIndex);
    }

    function transitionToSequence(nextIndex) {
        if (transitioning) return;
        transitioning = true;
        stage.classList.add("is-leaving");
        window.setTimeout(() => {
            showSequenceItem(nextIndex);
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

    function renderCompletion(result) {
        const completion = document.createElement("section");
        completion.className = "completion-panel";

        const card = document.createElement("div");
        card.className = "completion-card";

        const kicker = document.createElement("p");
        kicker.className = "test-kicker";
        kicker.textContent = quiz.dataset.testName.toUpperCase();
        card.append(kicker);

        const heading = document.createElement("h1");
        heading.textContent = "Test submitted";
        card.append(heading);

        const score = document.createElement("p");
        score.className = "completion-score";
        score.textContent = `Your score: ${result.score} / ${result.question_count}`;
        card.append(score);

        const missedHeading = document.createElement("p");
        missedHeading.className = "missed-heading";
        const missedQuestions = document.createElement("ol");
        missedQuestions.className = "missed-questions";

        if (result.incorrect_questions.length) {
            missedHeading.textContent = "Questions answered incorrectly";
            result.incorrect_questions.forEach(({ question_number }) => {
                const item = document.createElement("li");
                item.textContent = `Q${question_number}`;
                missedQuestions.append(item);
            });
            card.append(missedHeading, missedQuestions);
        } else {
            missedHeading.textContent = "All questions correct.";
            card.append(missedHeading);
        }

        const note = document.createElement("p");
        note.className = "completion-note";
        note.textContent = "Correct answers are not shown.";
        card.append(note);

        const returnLink = document.createElement("a");
        returnLink.className = "tactile-button primary-button";
        returnLink.href = quiz.dataset.nextUrl || quiz.dataset.centerUrl;
        returnLink.textContent = quiz.dataset.nextUrl
            ? "Continue to next vocabulary range"
            : "Return to test center";
        card.append(returnLink);

        completion.append(card);
        stage.replaceChildren(completion);
    }

    async function submitTest() {
        awaitingSubmissionRetry = false;
        nextButton.disabled = true;
        previousButton.disabled = true;
        nextButton.textContent = "Submitting…";
        error.hidden = true;

        try {
            const response = await fetch(quiz.dataset.submitUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    answers: Object.fromEntries(answers),
                    name: participantName.value.trim(),
                }),
            });
            const result = await response.json();
            if (
                !response.ok
                || result.submitted !== true
                || !Number.isInteger(result.score)
                || !Number.isInteger(result.question_count)
                || !Array.isArray(result.incorrect_questions)
            ) {
                throw new Error(result.error || "Your test could not be submitted. Please try again.");
            }
            renderCompletion(result);
            document.querySelector(".test-controls").hidden = true;
            counter.textContent = "Complete";
            progress.value = questions.length;
        } catch (submissionError) {
            error.textContent = submissionError.message;
            error.hidden = false;
            awaitingSubmissionRetry = true;
            controls.hidden = false;
            nextButton.disabled = false;
            previousButton.disabled = true;
            nextButton.textContent = "Retry submission";
        }
    }

    previousButton.addEventListener("click", () => {
        if (currentIndex === 0 || waitingForAudio || transitioning) return;
        for (let index = sequenceIndex - 1; index >= 0; index -= 1) {
            if (sequenceItems[index].type === "question") {
                transitionToSequence(index);
                return;
            }
        }
    });

    nextButton.addEventListener("click", async () => {
        if (waitingForAudio || transitioning) return;
        if (awaitingSubmissionRetry) {
            await submitTest();
            return;
        }
        if (!answers.has(questions[currentIndex].id)) {
            error.textContent = "Choose an answer before continuing.";
            error.hidden = false;
            return;
        }

        const question = questions[currentIndex];
        lockedAnswers.add(question.id);
        options.querySelectorAll(".answer-button").forEach((button) => {
            button.disabled = true;
        });
        if (question.audio) {
            waitingForAudio = true;
            nextButton.disabled = true;
            previousButton.disabled = true;
            nextButton.textContent = "Playing audio…";
            error.hidden = true;
            mediaError.hidden = true;
            try {
                await startAudio(`question:${question.id}`, question.audio);
            } catch (audioError) {
                mediaError.textContent = audioError.message;
                mediaError.hidden = false;
                waitingForAudio = false;
                nextButton.disabled = false;
                previousButton.disabled = currentIndex === 0;
                nextButton.textContent = "Retry audio";
                return;
            }
            waitingForAudio = false;
        }

        transitionToSequence(sequenceIndex + 1);
    });

    showSequenceItem(0);
})();
