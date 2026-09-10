const FORM_DEFINITIONS = [
    { key: "past", label: "Past", audio: "past audio" },
    { key: "base form", label: "Present", audio: "base form audio" },
    { key: "3rd person singular", label: "3rd person singular", audio: "3rd person audio" },
    { key: "future", label: "Future", audio: "future audio" },
    { key: "ING", label: "ING", audio: "ING audio" },
    { key: "past participle", label: "Past participle", audio: "past participle audio" },
    { key: "infinitive", label: "Infinitive", audio: "infinitive audio" }
];

let groups = [];
let selectedGroupIndex = 0;
let selectedSeriesIndex = 0;
let currentVerbIndex = 0;
let currentVerb = null;
let score = 0;
let attempts = new Map();
let completedForms = new Set();
const progressStorageKey = "feliponetica-conjugation-progress";
const savedUser = document.body.dataset.savedUser === "true";
let progressState = {};

document.addEventListener("DOMContentLoaded", () => {
    if (savedUser) beginGame();
    initializeGame();
});

async function initializeGame() {
    try {
        await loadProgress();
        const response = await fetch("/static/data/verb_conjugation.json");
        if (!response.ok) throw new Error("Unable to load verb_conjugation.json");
        const data = await response.json();
        groups = Object.entries(data).map(([name, group]) => ({ name, series: group.series || [] }));
        if (!groups.length || !groups.some(group => group.series.length)) throw new Error("No verb series found");
        renderSetList();
        renderProgress();
        selectGroup(0);
    } catch (error) {
        console.error(error);
        setStatus("The verb data could not be loaded. Check the JSON file.", "error");
    }
}

function beginGame() {
    document.getElementById("entry-gate").hidden = true;
    document.querySelector(".game").classList.add("ready");
}

function currentSeries() {
    return groups[selectedGroupIndex]?.series[selectedSeriesIndex];
}

function selectGroup(index) {
    selectedGroupIndex = index;
    const saved = getSavedProgress()[groups[index].name] || {};
    selectedSeriesIndex = Math.min(saved.completedSeries || 0, Math.max(groups[index].series.length - 1, 0));
    currentVerbIndex = saved.currentVerb || 0;
    score = saved.score || 0;
    document.getElementById("score").textContent = score;
    renderSetList();
    renderProgress();
    prepareSeries();
}

function prepareSeries() {
    const series = currentSeries();
    if (!series) return;
    currentVerb = series.verbs?.[0] || null;
    document.getElementById("start-button").hidden = false;
    document.getElementById("start-button").textContent = "Start series";
    document.getElementById("complete").hidden = true;
    document.getElementById("answer-grid").innerHTML = "";
    document.getElementById("series-title").textContent = `${groups[selectedGroupIndex].name} - ${series.title || `Series ${selectedSeriesIndex + 1}`}`;
    document.getElementById("verb-title").textContent = currentVerb ? currentVerb.verb : "No verbs in this series";
    document.getElementById("meaning").textContent = currentVerb ? getMeaning(currentVerb) : "";
    document.getElementById("prompt").textContent = `${series.verbs?.length || 0} verbs in this series`;
    setStatus("");
}

function startSeries() {
    if (!currentSeries()?.verbs?.length) return;
    currentVerbIndex = 0;
    loadVerb();
}

function loadVerb() {
    const series = currentSeries();
    currentVerb = series.verbs[currentVerbIndex];
    attempts = new Map();
    completedForms = new Set();
    document.getElementById("start-button").hidden = true;
    document.getElementById("complete").hidden = true;
    document.getElementById("verb-title").textContent = currentVerb.verb || currentVerb["base form"];
    document.getElementById("meaning").textContent = getMeaning(currentVerb);
    document.getElementById("prompt").textContent = `Verb ${currentVerbIndex + 1} of ${series.verbs.length}: choose the correct form in each area.`;
    renderAreas();
    setStatus("");
}

function renderAreas() {
    const grid = document.getElementById("answer-grid");
    grid.innerHTML = "";
    FORM_DEFINITIONS.forEach((form, areaIndex) => {
        const area = document.createElement("article");
        area.className = "answer-area";
        area.dataset.form = form.key;
        area.innerHTML = `<div class="area-title">${form.label}</div><div class="area-answer"></div><button class="choose-button" type="button">Choose answer</button><div class="option-menu" hidden></div>`;
        area.querySelector(".choose-button").addEventListener("click", () => showOptions(area, areaIndex));
        grid.appendChild(area);
    });
}

function showOptions(area, areaIndex) {
    if (completedForms.has(area.dataset.form)) return;
    const menu = area.querySelector(".option-menu");
    menu.innerHTML = "";
    menu.hidden = false;
    area.querySelector(".choose-button").disabled = true;
    const options = [];
    FORM_DEFINITIONS.forEach(form => {
        const value = currentVerb[form.key];
        if (value !== undefined && value !== "" && !options.some(option => option.value === value)) {
            options.push({ value, keys: FORM_DEFINITIONS.filter(match => currentVerb[match.key] === value).map(match => match.key) });
        }
    });
    shuffle(options).forEach(option => {
        const button = document.createElement("button");
        button.className = "option";
        button.type = "button";
        button.textContent = option.value;
        button.addEventListener("click", () => checkAnswer(area, areaIndex, option));
        menu.appendChild(button);
    });
}

function checkAnswer(area, areaIndex, selectedOption) {
    const formKey = area.dataset.form;
    if (completedForms.has(formKey)) return;
    const tries = (attempts.get(formKey) || 0) + 1;
    attempts.set(formKey, tries);
    if (!selectedOption.keys.includes(formKey)) {
        area.classList.remove("wrong");
        void area.offsetWidth;
        area.classList.add("wrong");
        playHelpAudio(areaIndex);
        setStatus("Not quite. Listen to the help and try again.", "error");
        area.querySelector(".choose-button").disabled = false;
        area.querySelector(".option-menu").hidden = true;
        return;
    }
    completedForms.add(formKey);
    attempts.set(formKey, tries);
    area.classList.remove("wrong");
    area.classList.add("correct");
    area.querySelector(".area-answer").textContent = currentVerb[formKey];
    area.querySelector(".choose-button").hidden = true;
    area.querySelector(".option-menu").hidden = true;
    addAudioLink(area, FORM_DEFINITIONS[areaIndex], currentVerb[formKey]);
    score += tries === 1 ? 2 : 1;
    document.getElementById("score").textContent = score;
    fireConfetti();
    setStatus(tries === 1 ? "Correct! Full points." : "Correct! Half points.", "success");
    if (completedForms.size === FORM_DEFINITIONS.length) finishVerb();
}

function finishVerb() {
    renderProgress();
    const series = currentSeries();
    if (currentVerbIndex < series.verbs.length - 1) {
        saveProgress(selectedSeriesIndex, currentVerbIndex + 1);
        setTimeout(() => { currentVerbIndex += 1; loadVerb(); }, 700);
        return;
    }
    saveProgress(selectedSeriesIndex + 1, 0);
    document.getElementById("complete").hidden = false;
    document.getElementById("complete-message").textContent = `${series.title || "This series"} is complete. Your score is ${score}.`;
    document.getElementById("next-button").hidden = selectedSeriesIndex >= groups[selectedGroupIndex].series.length - 1;
    setStatus("Series complete!", "success");
}

function nextSeries() {
    if (selectedSeriesIndex >= groups[selectedGroupIndex].series.length - 1) return;
    selectedSeriesIndex += 1;
    currentVerbIndex = 0;
    renderProgress();
    prepareSeries();
}

function getSavedProgress() {
    if (savedUser) return progressState;
    try {
        return JSON.parse(localStorage.getItem(progressStorageKey) || "{}");
    } catch (error) {
        return {};
    }
}

function saveProgress(completedSeries, currentVerb = 0) {
    const saved = getSavedProgress();
    saved[groups[selectedGroupIndex].name] = { completedSeries, score };
    progressState = saved;
    if (savedUser) {
        fetch("/api/conjugation-progress", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                group_name: groups[selectedGroupIndex].name,
                completed_series: completedSeries,
                current_verb: currentVerb,
                score
            })
        }).catch(error => console.error("Could not save progress", error));
    } else {
        localStorage.setItem(progressStorageKey, JSON.stringify(saved));
    }
}

async function loadProgress() {
    if (savedUser) {
        const response = await fetch("/api/conjugation-progress");
        const data = await response.json();
        progressState = data.progress || {};
    } else {
        progressState = getLocalProgress();
    }
}

function getLocalProgress() {
    try {
        return JSON.parse(localStorage.getItem(progressStorageKey) || "{}");
    } catch (error) {
        return {};
    }
}

function renderSetList() {
    const list = document.getElementById("set-list");
    list.innerHTML = "";
    groups.forEach((group, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `set-card${index === selectedGroupIndex ? " active" : ""}`;
        button.innerHTML = `<strong>${group.name}</strong><span>${group.series.length} series</span>`;
        button.addEventListener("click", () => selectGroup(index));
        list.appendChild(button);
    });
}

function renderProgress() {
    const lists = [document.getElementById("progress-list"), document.getElementById("progress-list-right")];
    if (!groups.length) return;
    lists.forEach(list => {
        if (!list) return;
        list.innerHTML = "";
        groups[selectedGroupIndex].series.forEach((series, index) => {
            const completed = index < selectedSeriesIndex ? series.verbs.length : index === selectedSeriesIndex ? currentVerbIndex + (completedForms.size === FORM_DEFINITIONS.length ? 1 : 0) : 0;
            const total = series.verbs?.length || 0;
            const row = document.createElement("div");
            row.className = "progress-row";
            row.innerHTML = `<div class="progress-label"><span>${series.title || `Series ${index + 1}`}</span><span>${Math.min(completed, total)}/${total}</span></div><div class="progress-track"><div class="progress-fill" style="width:${total ? Math.min(completed / total * 100, 100) : 0}%"></div></div>`;
            list.appendChild(row);
        });
    });
}

async function resolveAudioValue(form, text) {
    const keyCandidates = [
        form.audio,
        `${form.key} audio`,
        form.key === "3rd person singular" ? "3rd person audio" : "",
        form.key === "base form" ? "base form audio" : "",
        form.key === "past participle" ? "past participle audio" : "",
        form.key === "infinitive" ? "infinitive audio" : "",
        form.key === "ING" ? "ING audio" : "",
        form.key === "future" ? "future audio" : "",
        form.key === "past" ? "past audio" : ""
    ].filter(Boolean);

    for (const key of keyCandidates) {
        const value = currentVerb?.[key];
        if (value) return value;
    }

    return buildVerbAudioUrl(text, form.key);
}

async function addAudioLink(area, form, text) {
    const value = resolveAudioValue(form, text);
    if (!value) return;
    const exists = await audioUrlExists(value);
    if (!exists) return;
    const link = document.createElement("a");
    link.className = "audio-link";
    link.href = value;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "Play verb audio";
    area.appendChild(link);
}

async function playHelpAudio(areaIndex) {
    const form = FORM_DEFINITIONS[areaIndex];
    const audioUrl = resolveAudioValue(form, currentVerb?.[form.key] || currentVerb?.verb || "");
    if (!audioUrl) return;
    const exists = await audioUrlExists(audioUrl);
    if (!exists) return;
    const audio = new Audio(audioUrl);
    audio.play().catch(() => {});
}

function buildVerbAudioUrl(text, formKey = "") {
    const queue = [];
    const seen = new Set();
    const baseValues = [
        text,
        currentVerb?.verb,
        currentVerb?.["base form"],
        currentVerb?.["3rd person singular"],
        currentVerb?.["past"],
        currentVerb?.["ING"],
        currentVerb?.["past participle"],
        currentVerb?.["infinitive"],
        formKey ? currentVerb?.[formKey] : ""
    ].filter(Boolean);

    baseValues.forEach(value => {
        const cleaned = String(value).trim();
        if (!cleaned) return;
        const simple = cleaned.toLowerCase().replace(/^(to|will|would|can|could|should|must|may|might|have|has|had)\s+/i, "").trim();
        const words = simple.split(/\s+/).filter(Boolean);
        const lastWord = words.at(-1) || simple;
        const rootWord = lastWord.replace(/[^a-z]/gi, "").toLowerCase();
        const variants = [
            simple,
            lastWord,
            rootWord,
            rootWord.replace(/ing$/, ""),
            rootWord.replace(/s$/, ""),
            rootWord.replace(/es$/, ""),
            rootWord.replace(/ed$/, "")
        ].filter(Boolean);

        variants.forEach(variant => {
            const normalized = variant.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
            if (!normalized || seen.has(normalized)) return;
            seen.add(normalized);
            queue.push(normalized);
            const fbName = `FB_${normalized}`;
            if (!seen.has(fbName)) {
                seen.add(fbName);
                queue.push(fbName);
            }
        });
    });

    const audioRoot = "/static/audio/pronunciation%20audio/";
    for (const candidate of queue) {
        for (const extension of [".mp3", ".wav"]) {
            const fileName = `${candidate}${extension}`;
            return `${audioRoot}${encodeURIComponent(fileName).replace(/%20/g, " ")}`;
        }
    }
    return "";
}

async function audioUrlExists(url) {
    if (!url) return false;
    try {
        const response = await fetch(url, { method: "HEAD" });
        return response.ok;
    } catch (error) {
        try {
            const response = await fetch(url, { method: "GET" });
            return response.ok;
        } catch {
            return false;
        }
    }
}

function pronunciationUrl(text) {
    return "";
}

function getMeaning(verb) {
    return [1, 2, 3, 4].map(number => verb[`translation ${number}`]).filter(Boolean).join(" / ");
}

function shuffle(items) {
    for (let index = items.length - 1; index > 0; index -= 1) {
        const randomIndex = Math.floor(Math.random() * (index + 1));
        [items[index], items[randomIndex]] = [items[randomIndex], items[index]];
    }
    return items;
}

function setStatus(message, kind = "") {
    const status = document.getElementById("status");
    if (!status) return;
    status.textContent = message;
    status.className = `status ${kind}`;
}

function fireConfetti() {
    const holder = document.getElementById("confetti");
    holder.innerHTML = "";
    ["#ef6f61", "#177e89", "#f4c95d", "#2d9b70"].forEach((color, colorIndex) => {
        for (let index = 0; index < 7; index += 1) {
            const piece = document.createElement("i");
            piece.style.left = `${20 + Math.random() * 60}%`;
            piece.style.top = `${10 + Math.random() * 20}%`;
            piece.style.background = color;
            piece.style.animationDelay = `${(colorIndex * 7 + index) * 15}ms`;
            holder.appendChild(piece);
        }
    });
}

document.getElementById("start-button").addEventListener("click", startSeries);
document.getElementById("next-button").addEventListener("click", nextSeries);
