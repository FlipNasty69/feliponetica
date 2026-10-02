const pageType = document.body.dataset.page;

if (pageType === "levels") {
    loadLevels();
} else if (pageType === "play") {
    loadGame();
}

async function loadLevels() {
    const message = document.getElementById("levels-message");
    try {
        const response = await fetch("/games/word-order/api/levels");
        const levels = await response.json();
        if (!response.ok) throw new Error(levels.error || "No se pudieron cargar los niveles.");

        const grid = document.getElementById("levels-grid");
        const completedCount = levels.filter(level => level.status === "completed").length;
        document.getElementById("overall-progress-label").textContent = `${completedCount} of ${levels.length} levels complete`;
        document.getElementById("overall-progress-fill").style.width = `${levels.length ? completedCount / levels.length * 100 : 0}%`;
        grid.replaceChildren();

        levels.forEach(level => {
            const card = document.createElement(level.status === "locked" ? "article" : "a");
            card.className = `wo-level-card${level.status === "locked" ? " is-locked" : ""}${level.status === "completed" ? " is-completed" : ""}`;
            if (level.status !== "locked") card.href = `/games/word-order/level/${level.id}`;
            else card.setAttribute("aria-disabled", "true");

            const main = document.createElement("div");
            main.className = "wo-level-main";
            const number = document.createElement("span");
            number.className = "wo-level-number";
            number.textContent = `LEVEL ${level.id}${level.cefr ? ` · ${level.cefr}` : ""}`;
            const title = document.createElement("h2");
            title.textContent = level.name_en;
            const translation = document.createElement("p");
            translation.className = "wo-level-es";
            translation.textContent = level.name_es;
            main.append(number, title, translation);

            const badge = document.createElement("span");
            badge.className = "wo-level-badge";
            badge.textContent = level.status === "completed" ? "Completed" : level.status === "locked" ? "Locked" : "Start";

            const meta = document.createElement("div");
            meta.className = "wo-level-meta";
            meta.textContent = `${level.challenge_count} challenges`;
            const focus = document.createElement("p");
            focus.className = "wo-level-focus";
            focus.textContent = level.grammar_focus || "";
            const progress = document.createElement("div");
            progress.className = "wo-level-progress";
            const progressLabel = document.createElement("span");
            progressLabel.textContent = `${level.completion_percentage}% complete`;
            const track = document.createElement("div");
            track.className = "wo-progress-track";
            const fill = document.createElement("span");
            fill.style.width = `${level.completion_percentage}%`;
            track.append(fill);
            progress.append(progressLabel, track);
            card.append(main, badge, meta, focus, progress);
            grid.append(card);
        });
        if (!levels.length) message.textContent = "Todavía no hay niveles disponibles.";
    } catch (error) {
        message.textContent = error.message;
    }
}

let gameState = null;
let availableTiles = [];
let answerTiles = [];
let challengeStartedAt = Date.now();

async function loadGame() {
    const levelId = document.body.dataset.levelId;
    const sessionId = new URLSearchParams(location.search).get("session_id");
    try {
        const response = sessionId
            ? await fetch(`/games/word-order/api/session/${encodeURIComponent(sessionId)}`)
            : await fetch("/games/word-order/api/session", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ level_id: levelId })
            });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "No se pudo iniciar el nivel.");
        if (data.completed) {
            location.assign(`/games/word-order/result/${encodeURIComponent(data.session_id)}`);
            return;
        }
        gameState = data;
        const url = new URL(location.href);
        url.searchParams.set("session_id", data.session_id);
        history.replaceState(null, "", url);
        showChallenge(data);
    } catch (error) {
        document.getElementById("play-message").textContent = error.message;
        document.getElementById("check-answer").disabled = true;
    }
}

function showChallenge(data) {
    gameState = data;
    availableTiles = data.tokens.map((text, index) => ({ id: `${data.challenge_id}-${index}`, text }));
    answerTiles = [];
    challengeStartedAt = Date.now();
    document.getElementById("level-name-en").textContent = data.level_name_en;
    document.getElementById("level-name-es").textContent = data.level_name_es;
    document.getElementById("challenge-prompt").textContent = data.prompt_es;
    document.getElementById("skill-tag").textContent = data.skill_tag;
    document.getElementById("score").textContent = data.score;
    document.getElementById("streak-label").textContent = `Streak ${data.streak}`;
    document.getElementById("round-progress-label").textContent = `${data.challenge_number} / ${data.total_challenges}`;
    const percentage = (data.challenge_index / data.total_challenges) * 100;
    document.getElementById("round-progress-fill").style.width = `${percentage}%`;
    document.querySelector(".wo-round-progress [role=progressbar]").setAttribute("aria-valuenow", String(Math.round(percentage)));
    document.getElementById("play-message").textContent = "";
    document.getElementById("feedback").hidden = true;
    document.getElementById("continue-game").hidden = true;
    document.getElementById("continue-game").disabled = false;
    document.getElementById("check-answer").hidden = false;
    document.getElementById("check-answer").disabled = Boolean(data.checked);
    renderTiles();
    if (data.checked && data.feedback) showFeedback(data.feedback);
}

function renderTiles() {
    const bank = document.getElementById("word-bank");
    const answer = document.getElementById("answer-lane");
    bank.replaceChildren();
    answer.replaceChildren();
    availableTiles.forEach(tile => bank.append(createTileButton(tile, false)));
    answerTiles.forEach((tile, index) => {
        const item = document.createElement("div");
        item.className = "wo-answer-item";
        item.append(createTileButton(tile, true));
        const moveEarlier = document.createElement("button");
        moveEarlier.type = "button";
        moveEarlier.className = "wo-reorder";
        moveEarlier.textContent = "←";
        moveEarlier.setAttribute("aria-label", `Move ${tile.text} earlier`);
        moveEarlier.title = "Move earlier";
        moveEarlier.disabled = index === 0 || Boolean(gameState.checked);
        moveEarlier.addEventListener("click", () => moveAnswerTile(index, -1));
        const moveLater = document.createElement("button");
        moveLater.type = "button";
        moveLater.className = "wo-reorder";
        moveLater.textContent = "→";
        moveLater.setAttribute("aria-label", `Move ${tile.text} later`);
        moveLater.title = "Move later";
        moveLater.disabled = index === answerTiles.length - 1 || Boolean(gameState.checked);
        moveLater.addEventListener("click", () => moveAnswerTile(index, 1));
        item.append(moveEarlier, moveLater);
        answer.append(item);
    });
}

function createTileButton(tile, selected) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "wo-tile";
    button.textContent = tile.text;
    button.disabled = Boolean(gameState.checked);
    button.setAttribute("aria-label", selected ? `Remove ${tile.text}` : `Add ${tile.text}`);
    button.addEventListener("click", () => {
        if (gameState.checked) return;
        if (selected) {
            answerTiles = answerTiles.filter(item => item.id !== tile.id);
            availableTiles.push(tile);
        } else {
            availableTiles = availableTiles.filter(item => item.id !== tile.id);
            answerTiles.push(tile);
        }
        renderTiles();
    });
    return button;
}

function moveAnswerTile(index, direction) {
    const target = index + direction;
    if (target < 0 || target >= answerTiles.length || gameState.checked) return;
    [answerTiles[index], answerTiles[target]] = [answerTiles[target], answerTiles[index]];
    renderTiles();
}

function joinAnswer(tokens) {
    return tokens.map(tile => tile.text).join(" ").replace(/\s+([.,?!])/g, "$1");
}

async function checkCurrentAnswer() {
    if (!gameState || gameState.checked) return;
    const checkButton = document.getElementById("check-answer");
    checkButton.disabled = true;
    try {
        const response = await fetch("/games/word-order/check", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                session_id: gameState.session_id,
                answer: joinAnswer(answerTiles),
                response_time_ms: Date.now() - challengeStartedAt
            })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "No se pudo revisar la respuesta.");
        gameState.checked = true;
        gameState.score += data.score_change;
        gameState.streak = data.streak;
        gameState.feedback = data;
        showFeedback(data);
        renderTiles();
    } catch (error) {
        checkButton.disabled = false;
        document.getElementById("play-message").textContent = error.message;
    }
}

function showFeedback(data) {
    const feedback = document.getElementById("feedback");
    feedback.className = `wo-feedback ${data.correct ? "is-correct" : "is-incorrect"}`;
    feedback.replaceChildren();
    const heading = document.createElement("strong");
    heading.textContent = data.correct ? "¡Correcto!" : "Casi. Revisa el orden.";
    feedback.append(heading);
    if (!data.correct) {
        const answer = document.createElement("p");
        answer.textContent = `La respuesta correcta es: ${data.correct_answer}`;
        feedback.append(answer);
    }
    if (data.explanation_es) {
        const explanation = document.createElement("p");
        explanation.textContent = data.explanation_es;
        feedback.append(explanation);
    }
    feedback.hidden = false;
    document.getElementById("score").textContent = gameState.score;
    document.getElementById("streak-label").textContent = `Streak ${data.streak}`;
    document.getElementById("check-answer").hidden = true;
    const continueButton = document.getElementById("continue-game");
    continueButton.textContent = "Continue";
    continueButton.hidden = false;
    continueButton.focus();
}

async function continueGame() {
    const button = document.getElementById("continue-game");
    button.disabled = true;
    try {
        const response = await fetch("/games/word-order/api/continue", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: gameState.session_id })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "No se pudo continuar.");
        if (data.completed) {
            location.assign(data.result_url);
            return;
        }
        showChallenge(data.challenge);
    } catch (error) {
        document.getElementById("play-message").textContent = error.message;
        button.disabled = false;
    }
}

if (pageType === "play") {
    document.getElementById("check-answer").addEventListener("click", checkCurrentAnswer);
    document.getElementById("continue-game").addEventListener("click", continueGame);
}