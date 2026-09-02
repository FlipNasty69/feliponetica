/* =========================================================
   FELIPONETICA
   VERB CONJUGATION GAME ENGINE
   ========================================================= */


/* =========================================================
   GAME DATA
   ========================================================= */

let conjugationData = null;

let currentVerbIndex = 0;

let currentVerb = null;

let completedAreas = new Set();


/* =========================================================
   THE SEVEN PLAYABLE FORMS
   ========================================================= */

const playableForms = [
    "past",
    "present",
    "third_person",
    "future",
    "infinitive",
    "ing",
    "past_participle"
];


/* =========================================================
   START
   ========================================================= */

document.addEventListener(
    "DOMContentLoaded",
    initializeConjugationGame
);


/* =========================================================
   LOAD JSON
   ========================================================= */

async function initializeConjugationGame() {

    try {

        const response = await fetch(
            "/static/data/verb_conjugation.json"
        );

        if (!response.ok) {
            throw new Error(
                "Could not load verb_conjugation.json"
            );
        }

        conjugationData =
            await response.json();


        if (
            !conjugationData.verbs ||
            conjugationData.verbs.length === 0
        ) {

            throw new Error(
                "No verbs were found in the JSON file."
            );

        }


        loadVerb(0);


    } catch (error) {

        console.error(error);

        const feedback =
            document.getElementById(
                "conjugation-feedback"
            );

        feedback.textContent =
            "There was a problem loading the verb game.";

        feedback.classList.add(
            "feedback-error"
        );

    }

}


/* =========================================================
   LOAD VERB
   ========================================================= */

function loadVerb(index) {

    if (!conjugationData) {
        return;
    }


    if (
        index < 0 ||
        index >= conjugationData.verbs.length
    ) {
        index = 0;
    }


    currentVerbIndex = index;

    currentVerb =
        conjugationData.verbs[
            currentVerbIndex
        ];


    completedAreas =
        new Set();


    clearFeedback();

    displayBaseForm();

    createGameAreas();

}


/* =========================================================
   DISPLAY BASE FORM
   ========================================================= */

function displayBaseForm() {

    const baseForm =
        document.getElementById(
            "base-form"
        );


    baseForm.textContent =
        currentVerb.base;

}


/* =========================================================
   CREATE THE SEVEN GAME AREAS
   ========================================================= */

function createGameAreas() {

    playableForms.forEach(
        form => {

            const area =
                document.querySelector(
                    `[data-form="${form}"]`
                );


            const optionsContainer =
                document.getElementById(
                    `options-${form}`
                );


            if (!area || !optionsContainer) {
                return;
            }


            area.classList.remove(
                "correct",
                "incorrect"
            );


            const helpButton =
                area.querySelector(
                    ".help-btn"
                );


            if (helpButton) {

                helpButton.hidden =
                    true;

                helpButton.classList.remove(
                    "help-active"
                );

            }


            optionsContainer.innerHTML =
                "";


            createOptions(
                form,
                optionsContainer
            );

        }
    );

}


/* =========================================================
   CREATE OPTIONS
   ========================================================= */

function createOptions(
    targetForm,
    container
) {

    const options =
        getAllSevenOptions();


    shuffleArray(options);


    options.forEach(
        option => {

            const button =
                document.createElement(
                    "button"
                );


            button.type =
                "button";


            button.className =
                "verb-option";


            button.textContent =
                option.text;


            /*
               The ID is important.

               Some regular verbs have duplicate
               visible forms.

               Example:

               worked
               worked

               They look identical, but their internal
               IDs are different.
            */

            button.dataset.optionId =
                option.id;


            button.addEventListener(
                "click",
                () => {

                    checkAnswer(
                        targetForm,
                        option.id,
                        container
                    );

                }
            );


            container.appendChild(
                button
            );

        }
    );

}


/* =========================================================
   GET ALL SEVEN OPTIONS
   ========================================================= */

function getAllSevenOptions() {

    return [

        {
            id: "past",
            text: currentVerb.past
        },

        {
            id: "present",
            text: currentVerb.present
        },

        {
            id: "third_person",
            text: currentVerb.third_person
        },

        {
            id: "future",
            text: currentVerb.future
        },

        {
            id: "infinitive",
            text: currentVerb.infinitive
        },

        {
            id: "ing",
            text: currentVerb.ing
        },

        {
            id: "past_participle",
            text: currentVerb.past_participle
        }

    ];

}


/* =========================================================
   CHECK ANSWER
   ========================================================= */

function checkAnswer(
    targetForm,
    selectedOptionId,
    container
) {

    /*
       Don't allow the student to keep answering
       an area that has already been completed.
    */

    if (
        completedAreas.has(targetForm)
    ) {
        return;
    }


    const area =
        document.querySelector(
            `[data-form="${targetForm}"]`
        );


    const correct =
        selectedOptionId === targetForm;


    if (correct) {

        handleCorrectAnswer(
            area,
            container
        );

    } else {

        handleWrongAnswer(
            area
        );

    }

}


/* =========================================================
   CORRECT ANSWER
   ========================================================= */

function handleCorrectAnswer(
    area,
    container
) {

    completedAreas.add(
        area.dataset.form
    );


    area.classList.remove(
        "incorrect"
    );


    area.classList.add(
        "correct"
    );


    /*
       Disable all choices in this area.
    */

    const buttons =
        container.querySelectorAll(
            ".verb-option"
        );


    buttons.forEach(
        button => {

            button.disabled =
                true;

        }
    );


    /*
       Hide Help if it was active.
    */

    const helpButton =
        area.querySelector(
            ".help-btn"
        );


    if (helpButton) {
        helpButton.hidden =
            true;
    }


    playAudio(
        "hooray-audio"
    );


    showFeedback(
        "Hooray! ✓",
        "feedback-success"
    );


    /*
       Check whether all seven areas
       have been completed.
    */

    if (
        completedAreas.size ===
        playableForms.length
    ) {

        showGameComplete();

    }

}


/* =========================================================
   WRONG ANSWER
   ========================================================= */

function handleWrongAnswer(
    area
) {

    area.classList.remove(
        "correct"
    );


    area.classList.add(
        "incorrect"
    );


    playAudio(
        "too-bad-audio"
    );


    showFeedback(
        "Too bad!",
        "feedback-error"
    );


    /*
       Turn on the Help button.
    */

    const helpButton =
        area.querySelector(
            ".help-btn"
        );


    if (helpButton) {

        helpButton.hidden =
            false;

        helpButton.classList.add(
            "help-active"
        );


        /*
           Make sure it only gets
           one event listener.
        */

        if (
            helpButton.dataset.bound !== "true"
        ) {

            helpButton.addEventListener(
                "click",
                () => {

                    showHelp(
                        area.dataset.form
                    );

                }
            );


            helpButton.dataset.bound =
                "true";

        }

    }


    /*
       Remove the red state after a moment
       so the student can try again.
    */

    setTimeout(
        () => {

            if (
                !completedAreas.has(
                    area.dataset.form
                )
            ) {

                area.classList.remove(
                    "incorrect"
                );

            }

        },
        700
    );

}


/* =========================================================
   HELP
   ========================================================= */

function showHelp(form) {

    const helpMessages = {

        past:
            "PAST: Use the past form of the verb.",

        present:
            "PRESENT: Use the base form.",

        third_person:
            "3RD PERSON SINGULAR: Add S to the base form.",

        future:
            "FUTURE: WILL + base form.",

        infinitive:
            "INFINITIVE: TO + base form.",

        ing:
            "-ING: Base form + ING.",

        past_participle:
            "PAST PARTICIPLE: Use the past participle form."

    };


    const message =
        helpMessages[form] ||
        "Look carefully at the form required.";


    showFeedback(
        message,
        "feedback-help"
    );

}


/* =========================================================
   GAME COMPLETE
   ========================================================= */

function showGameComplete() {

    showFeedback(
        "Excellent! You found all seven forms!",
        "feedback-success"
    );

}


/* =========================================================
   NEXT VERB
   ========================================================= */

document
    .getElementById("next-verb-btn")
    .addEventListener(
        "click",
        () => {

            if (!conjugationData) {
                return;
            }


            let nextIndex =
                currentVerbIndex + 1;


            if (
                nextIndex >=
                conjugationData.verbs.length
            ) {

                nextIndex = 0;

            }


            loadVerb(
                nextIndex
            );

        }
    );


/* =========================================================
   RESTART
   ========================================================= */

document
    .getElementById("restart-btn")
    .addEventListener(
        "click",
        () => {

            loadVerb(
                currentVerbIndex
            );

        }
    );


/* =========================================================
   AUDIO
   ========================================================= */

function playAudio(
    audioId
) {

    const audio =
        document.getElementById(
            audioId
        );


    if (!audio) {
        return;
    }


    audio.currentTime = 0;


    audio.play().catch(
        () => {
            /*
               Ignore browser autoplay/audio
               restrictions.
            */
        }
    );

}


/* =========================================================
   FEEDBACK
   ========================================================= */

function showFeedback(
    message,
    className
) {

    const feedback =
        document.getElementById(
            "conjugation-feedback"
        );


    feedback.textContent =
        message;


    feedback.className =
        "conjugation-feedback";


    feedback.classList.add(
        className
    );

}


function clearFeedback() {

    const feedback =
        document.getElementById(
            "conjugation-feedback"
        );


    feedback.textContent =
        "";


    feedback.className =
        "conjugation-feedback";

}


/* =========================================================
   SHUFFLE
   ========================================================= */

function shuffleArray(array) {

    for (
        let i = array.length - 1;
        i > 0;
        i--
    ) {

        const j =
            Math.floor(
                Math.random() *
                (i + 1)
            );


        [
            array[i],
            array[j]
        ] = [
            array[j],
            array[i]
        ];

    }


    return array;

}