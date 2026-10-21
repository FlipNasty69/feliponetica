(() => {
    const setupScreen = document.getElementById("setup-screen");
    const playScreen = document.getElementById("play-screen");
    const resultsScreen = document.getElementById("results-screen");
    const levelTitle = document.getElementById("level-title");
    const progressLabel = document.getElementById("progress-label");
    const progressFill = document.getElementById("progress-fill");
    const progressTrack = document.querySelector(".progress-track");
    const liveScore = document.getElementById("live-score");
    const challengeGrid = document.getElementById("challenge-grid");
    const columnLabels = document.getElementById("column-labels");
    const wordBank = document.getElementById("word-bank");
    const feedback = document.getElementById("feedback");
    const errorMessage = document.getElementById("error-message");
    const playError = document.getElementById("play-error");
    const startButton = document.getElementById("start-button");
    const levelSelection = document.getElementById("level-selection");
    const exerciseSelection = document.getElementById("exercise-selection");
    const exerciseOptions = document.getElementById("exercise-options");
    const feedbackDelay = 850;

    let selectedLevel = "";
    let level = "";
    let batches = [];
    let batchIndex = 0;
    let questionIndex = 0;
    let total = 0;
    let completed = 0;
    let score = 0;
    let currentBatch = null;
    let assignments = [];
    let selectedTile = null;
    let isChecking = false;

    document.querySelector("[data-level='level1']").addEventListener("click", async () => {
        errorMessage.classList.add("hidden");
        exerciseOptions.replaceChildren();
        selectedLevel = "";
        startButton.disabled = true;
        startButton.classList.add("hidden");
        levelSelection.classList.add("hidden");
        exerciseSelection.classList.remove("hidden");
        try {
            const payload = await readPayload(await fetch("/question-game/api/exercises"));
            if (!payload.exercises.length) {
                throw new Error("No Level 1 exercises are available.");
            }
            payload.exercises.forEach((exercise) => {
                const button = document.createElement("button");
                button.type = "button";
                button.className = "level-option";
                button.setAttribute("aria-pressed", "false");

                const icon = document.createElement("span");
                icon.className = "level-icon";
                icon.setAttribute("aria-hidden", "true");
                icon.textContent = String(exercise.total);

                const title = document.createElement("strong");
                title.textContent = exercise.title;

                const description = document.createElement("span");
                description.textContent = `${exercise.description} ${exercise.total} questions.`;
                button.append(icon, title, description);
                button.addEventListener("click", () => {
                    selectedLevel = exercise.id;
                    exerciseOptions.querySelectorAll(".level-option").forEach((option) => {
                        const selected = option === button;
                        option.classList.toggle("selected", selected);
                        option.setAttribute("aria-pressed", String(selected));
                    });
                    startButton.disabled = false;
                    startButton.classList.remove("hidden");
                });
                exerciseOptions.appendChild(button);
            });
        } catch (error) {
            showError(errorMessage, error.message || "The exercises could not be loaded.");
        }
    });

    document.getElementById("back-to-levels").addEventListener("click", () => {
        exerciseSelection.classList.add("hidden");
        levelSelection.classList.remove("hidden");
        startButton.classList.add("hidden");
        startButton.disabled = true;
        selectedLevel = "";
        errorMessage.classList.add("hidden");
    });

    function setScreen(screen) {
        setupScreen.classList.toggle("hidden", screen !== "setup");
        playScreen.classList.toggle("hidden", screen !== "play");
        resultsScreen.classList.toggle("hidden", screen !== "results");
    }

    function showError(element, message) {
        element.textContent = message;
        element.classList.remove("hidden");
    }

    async function readPayload(response) {
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || "The question game request failed.");
        }
        return payload;
    }

    function updateProgress() {
        const questionNumber = Math.min(completed + 1, total);
        progressLabel.textContent = `Question ${questionNumber} of ${total}`;
        progressFill.style.width = `${(completed / total) * 100}%`;
        progressTrack.setAttribute("aria-valuemax", String(total));
        progressTrack.setAttribute("aria-valuenow", String(completed));
        liveScore.textContent = `${score} pts`;
    }

    function renderBatch() {
        const question = currentBatch.questions[questionIndex];
        const assignedTileIds = new Set(assignments.filter(Boolean));
        challengeGrid.replaceChildren();
        columnLabels.replaceChildren();
        wordBank.replaceChildren();
        const slotCount = question.slot_labels.length;
        const gridColumns = `repeat(${slotCount}, minmax(0, 1fr))`;
        columnLabels.style.gridTemplateColumns = gridColumns;

        const card = document.createElement("article");
        card.className = "challenge-card";
        card.dataset.questionId = question.id;

        const prompt = document.createElement("p");
        prompt.className = "spanish-prompt";
        prompt.textContent = question.prompt;
        card.appendChild(prompt);

        const slots = document.createElement("div");
        slots.className = "answer-slots";
        slots.style.gridTemplateColumns = gridColumns;
        question.slot_labels.forEach((label) => {
            const columnLabel = document.createElement("span");
            columnLabel.textContent = label;
            columnLabels.appendChild(columnLabel);
        });
        assignments.forEach((tileId, slotIndex) => {
            const slotLabel = question.slot_labels[slotIndex];
            const slot = document.createElement("button");
            slot.type = "button";
            slot.className = `answer-slot${tileId ? " filled" : ""}`;
            slot.setAttribute(
                "aria-label",
                `${slotLabel}: ${tileId ? "filled" : "empty"}`
            );
            slot.textContent = tileId
                ? currentBatch.word_bank.find((tile) => tile.id === tileId).word
                : `Drop ${slotLabel}`;
            slot.disabled = isChecking;
            slot.addEventListener("click", () => {
                if (isChecking) {
                    return;
                }
                if (tileId) {
                    assignments[slotIndex] = null;
                    selectedTile = null;
                    playError.classList.add("hidden");
                    renderBatch();
                } else if (selectedTile) {
                    assignTile(slotIndex, selectedTile);
                }
            });
            slot.addEventListener("dragover", (event) => event.preventDefault());
            slot.addEventListener("drop", (event) => {
                event.preventDefault();
                if (isChecking) {
                    return;
                }
                const tile = event.dataTransfer.getData("text/plain");
                if (tile) {
                    assignTile(slotIndex, tile);
                }
            });
            slots.appendChild(slot);
        });
        card.appendChild(slots);
        challengeGrid.appendChild(card);

        currentBatch.word_bank
            .filter((tile) => !assignedTileIds.has(tile.id))
            .forEach((tile) => {
                const button = document.createElement("button");
                button.type = "button";
                button.className = `word-tile${selectedTile === tile.id ? " selected" : ""}`;
                button.draggable = !isChecking;
                button.disabled = isChecking;
                button.textContent = tile.word;
                button.setAttribute("aria-label", `Word tile: ${tile.word}`);
                button.addEventListener("click", () => {
                    if (isChecking) {
                        return;
                    }
                    selectedTile = selectedTile === tile.id ? null : tile.id;
                    renderBatch();
                });
                button.addEventListener("dragstart", (event) => {
                    event.dataTransfer.setData("text/plain", tile.id);
                    event.dataTransfer.effectAllowed = "move";
                });
                wordBank.appendChild(button);
            });
    }

    function assignTile(slotIndex, tileId) {
        assignments.forEach((previousTileId, previousIndex) => {
            if (previousTileId === tileId) {
                assignments[previousIndex] = null;
            }
        });
        assignments[slotIndex] = tileId;
        selectedTile = null;
        playError.classList.add("hidden");
        feedback.className = "feedback hidden";
        feedback.textContent = "";
        renderBatch();
        if (assignments.every(Boolean)) {
            checkCurrentAnswer();
        }
    }

    async function checkCurrentAnswer() {
        isChecking = true;
        playError.classList.add("hidden");
        renderBatch();
        const question = currentBatch.questions[questionIndex];
        const assignedIds = [...assignments];
        try {
            const response = await fetch("/question-game/api/check", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    level,
                    answers: [{
                        id: question.id,
                        words: assignedIds.map((tileId) =>
                            currentBatch.word_bank.find((tile) => tile.id === tileId).word
                        ),
                    }],
                }),
            });
            const payload = await readPayload(response);
            const result = payload.results[0];
            const card = challengeGrid.querySelector(
                `[data-question-id="${CSS.escape(question.id)}"]`
            );
            card.classList.add(result.correct ? "correct" : "incorrect");
            feedback.className = `feedback ${result.correct ? "correct" : "incorrect"}`;
            feedback.textContent = result.correct
                ? "Correct!"
                : `Not quite. The answer is ${result.correct_answer.join(" ")}.`;
            feedback.classList.remove("hidden");

            if (result.correct) {
                score += 10;
            }

            window.setTimeout(() => {
                completed += 1;
                updateProgress();
                if (completed === total) {
                    showResults();
                    return;
                }
                questionIndex += 1;
                if (questionIndex === currentBatch.questions.length) {
                    batchIndex += 1;
                    questionIndex = 0;
                    currentBatch = batches[batchIndex];
                }
                assignments = new Array(
                    currentBatch.questions[questionIndex].slot_labels.length
                ).fill(null);
                selectedTile = null;
                isChecking = false;
                feedback.className = "feedback hidden";
                feedback.textContent = "";
                renderBatch();
                updateProgress();
            }, feedbackDelay);
        } catch (error) {
            isChecking = false;
            showError(
                playError,
                `${error.message || "Your answer could not be checked."} Change a word to try again.`
            );
            renderBatch();
        }
    }

    function showBatch() {
        currentBatch = batches[batchIndex];
        questionIndex = 0;
        assignments = new Array(
            currentBatch.questions[questionIndex].slot_labels.length
        ).fill(null);
        selectedTile = null;
        isChecking = false;
        playError.classList.add("hidden");
        feedback.className = "feedback hidden";
        feedback.textContent = "";
        updateProgress();
        renderBatch();
    }

    function showResults() {
        setScreen("results");
        progressFill.style.width = "100%";
        progressTrack.setAttribute("aria-valuenow", String(total));
        document.getElementById("result-score").textContent = `${score} / ${total * 10} points`;
        document.getElementById("result-message").textContent = score === total * 10
            ? "Perfect round! You built every question correctly."
            : "Nice work. Replay the level to practice the questions you missed.";
    }

    startButton.addEventListener("click", async () => {
        startButton.disabled = true;
        errorMessage.classList.add("hidden");
        try {
            const params = new URLSearchParams({ level: selectedLevel });
            const payload = await readPayload(
                await fetch(`/question-game/api/round?${params}`)
            );
            level = payload.level;
            levelTitle.textContent = payload.title;
            total = payload.total;
            batches = payload.batches;
            batchIndex = 0;
            completed = 0;
            score = 0;
            setScreen("play");
            showBatch();
        } catch (error) {
            showError(errorMessage, error.message || "The round could not be loaded.");
        } finally {
            startButton.disabled = false;
        }
    });

    document.getElementById("play-again-button").addEventListener("click", () => {
        setScreen("setup");
        errorMessage.classList.add("hidden");
    });
})();
