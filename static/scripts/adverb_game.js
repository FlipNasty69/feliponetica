(() => {
    const setupScreen = document.getElementById("setup-screen");
    const questionScreen = document.getElementById("question-screen");
    const resultsScreen = document.getElementById("results-screen");
    const progressRow = document.getElementById("progress-row");
    const progressFill = document.getElementById("progress-fill");
    const progressTrack = document.querySelector(".progress-track");
    const questionCount = document.getElementById("question-count");
    const liveScore = document.getElementById("live-score");
    const questionKicker = document.getElementById("question-kicker");
    const questionPrompt = document.getElementById("question-prompt");
    const sentenceCard = document.getElementById("sentence-card");
    const answerOptions = document.getElementById("answer-options");
    const feedback = document.getElementById("feedback");
    const nextButton = document.getElementById("next-button");
    const errorMessage = document.getElementById("error-message");
    const categorySelect = document.getElementById("category-select");
    const startButton = document.getElementById("start-button");
    const yesNoOptions = [
        { value: true, label: "Yes, that's right" },
        { value: false, label: "No, fix the placement" },
    ];

    let mode = "meaning";
    let questions = [];
    let questionIndex = 0;
    let score = 0;

    document.querySelectorAll(".mode-option").forEach((button) => {
        button.addEventListener("click", () => {
            mode = button.dataset.mode;
            document.querySelectorAll(".mode-option").forEach((option) => {
                const selected = option === button;
                option.classList.toggle("selected", selected);
                option.setAttribute("aria-pressed", String(selected));
            });
        });
    });

    function showError(message) {
        errorMessage.textContent = message;
        errorMessage.classList.remove("hidden");
    }

    function setScreen(screen) {
        setupScreen.classList.toggle("hidden", screen !== "setup");
        questionScreen.classList.toggle("hidden", screen !== "question");
        resultsScreen.classList.toggle("hidden", screen !== "results");
        progressRow.classList.toggle("hidden", screen !== "question");
    }

    function startQuestion() {
        const question = questions[questionIndex];
        const total = questions.length;
        questionCount.textContent = `Question ${questionIndex + 1} of ${total}`;
        progressFill.style.width = `${(questionIndex / total) * 100}%`;
        progressTrack.setAttribute("aria-valuemax", String(total));
        progressTrack.setAttribute("aria-valuenow", String(questionIndex));
        liveScore.textContent = `${score} pts`;
        questionKicker.textContent = question.category.replaceAll("_", " ");
        questionPrompt.textContent = question.prompt;
        sentenceCard.classList.toggle("hidden", mode !== "placement");
        sentenceCard.textContent = mode === "placement" ? question.sentence : "";
        feedback.className = "feedback hidden";
        feedback.textContent = "";
        nextButton.classList.add("hidden");
        answerOptions.replaceChildren();

        const choices = mode === "meaning"
            ? question.choices.map((choice) => ({ value: choice, label: choice }))
            : yesNoOptions;
        choices.forEach((choice) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "answer-option";
            button.textContent = choice.label;
            button.addEventListener("click", () => checkAnswer(button, choice.value, question));
            answerOptions.appendChild(button);
        });
    }

    function checkAnswer(selectedButton, answer, question) {
        const isCorrect = answer === question.answer;
        if (isCorrect) {
            score += 10;
        }
        liveScore.textContent = `${score} pts`;
        answerOptions.querySelectorAll("button").forEach((button) => {
            button.disabled = true;
        });
        if (mode === "meaning") {
            answerOptions.querySelectorAll("button").forEach((button) => {
                if (button.textContent === question.answer) {
                    button.classList.add("correct");
                }
            });
        } else if (isCorrect) {
            selectedButton.classList.add("correct");
        } else {
            selectedButton.classList.add("incorrect");
        }

        feedback.className = `feedback ${isCorrect ? "correct" : "incorrect"}`;
        if (mode === "meaning") {
            feedback.textContent = isCorrect
                ? `Correct! ${question.adverb} means ${question.answer}.`
                : `Not quite. ${question.adverb} means ${question.answer}.`;
        } else {
            const result = question.answer
                ? `Yes. “${question.adverb}” is correctly placed ${question.position}.`
                : `No. “${question.adverb}” belongs ${question.position}.`;
            feedback.textContent = `${isCorrect ? "Correct!" : "Not quite."} ${result} ${question.spanish}`;
        }
        nextButton.textContent = questionIndex + 1 === questions.length
            ? "See your score"
            : "Next question";
        nextButton.classList.remove("hidden");
    }

    function showResults() {
        setScreen("results");
        progressFill.style.width = "100%";
        progressTrack.setAttribute("aria-valuenow", String(questions.length));
        document.getElementById("result-score").textContent = `${score} / ${questions.length * 10} points`;
        document.getElementById("result-message").textContent = score === questions.length * 10
            ? "Perfect round! You know your adverbs."
            : "Nice work. Play another round to keep practicing.";
    }

    startButton.addEventListener("click", async () => {
        startButton.disabled = true;
        errorMessage.classList.add("hidden");
        const params = new URLSearchParams({
            mode,
            category: categorySelect.value,
            count: "10",
        });
        try {
            const response = await fetch(`/adverb-game/api/round?${params}`);
            const payload = await response.json();
            if (!response.ok) {
                throw new Error(payload.error || "The round could not be loaded.");
            }
            questions = payload.questions;
            if (!questions.length) {
                throw new Error("There are no questions for this selection.");
            }
            questionIndex = 0;
            score = 0;
            setScreen("question");
            startQuestion();
        } catch (error) {
            showError(error.message || "The round could not be loaded.");
        } finally {
            startButton.disabled = false;
        }
    });

    nextButton.addEventListener("click", () => {
        questionIndex += 1;
        if (questionIndex === questions.length) {
            showResults();
            return;
        }
        startQuestion();
    });

    document.getElementById("play-again-button").addEventListener("click", () => {
        setScreen("setup");
        errorMessage.classList.add("hidden");
    });
})();
