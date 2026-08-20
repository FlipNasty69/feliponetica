const mainAudio = document.getElementById('main-audio');
const hintAudio = document.getElementById('hint-audio');
const visualArea = document.getElementById('visual-area');
const quizArea = document.getElementById('quiz-area');
const optionsContainer = document.getElementById('options-container');
const startBtn = document.getElementById('start-btn');
const hintMessage = document.getElementById('hint-message');

let moduleData = null;
let currentEventIndex = 0;

// 1. Fetch the script for whichever module the student clicked
fetch(`/static/data/${MODULE_ID}.json`)
    .then(response => {
        if (!response.ok) throw new Error("Module data not found!");
        return response.json();
    })
    .then(data => {
        moduleData = data;
        document.getElementById('module-title').innerText = data.title;
        mainAudio.src = data.mainAudioUrl;
    })
    .catch(error => {
        document.getElementById('module-title').innerText = "Error: Could not load module.";
        console.error(error);
    });

// 2. Start the lesson when clicked
startBtn.addEventListener('click', () => {
    startBtn.classList.add('hidden');
    mainAudio.play();
});

// 3. Listen to the audio timer constantly
mainAudio.addEventListener('timeupdate', () => {
    if (!moduleData || currentEventIndex >= moduleData.events.length) return;

    let currentTime = mainAudio.currentTime;
    let nextEvent = moduleData.events[currentEventIndex];

    // If the audio reaches the timestamp for the next event, pause and show it
    if (currentTime >= nextEvent.time) {
        mainAudio.pause(); // Pause your teaching audio
        triggerEvent(nextEvent);
    }
});

// 4. Show the Image or the Quiz
function triggerEvent(event) {
    // Hide everything first to give a clean slate
    visualArea.classList.add('hidden');
    quizArea.classList.add('hidden');
    hintMessage.classList.add('hidden');

    if (event.type === 'image') {
        visualArea.innerHTML = `<img src="${event.imageUrl}" class="popup-img">`;
        
        // Create a button so the student can continue after looking at the image
        let continueBtn = document.createElement('button');
        continueBtn.innerText = "Got it, continue";
        continueBtn.className = "action-btn";
        continueBtn.onclick = () => {
            currentEventIndex++;
            visualArea.classList.add('hidden');
            mainAudio.play();
        };
        
        visualArea.appendChild(continueBtn);
        visualArea.classList.remove('hidden');
    } 
    else if (event.type === 'quiz') {
        document.getElementById('question-text').innerText = event.question;
        optionsContainer.innerHTML = ''; // Clear out any old buttons

        // Create a button for every answer option in your JSON script
        event.options.forEach(option => {
            let btn = document.createElement('button');
            btn.innerText = option;
            btn.className = "action-btn";
            btn.onclick = () => handleAnswer(option, event);
            optionsContainer.appendChild(btn);
        });

        quizArea.classList.remove('hidden');
    }
}

// 5. The Wrong Answer Loop
function handleAnswer(selectedOption, event) {
    if (selectedOption === event.correctAnswer) {
        // Right Answer! Hide the quiz, advance the script, and resume the lesson.
        quizArea.classList.add('hidden');
        hintMessage.classList.add('hidden');
        currentEventIndex++;
        mainAudio.play(); 
    } else {
        // Wrong Answer! Show the warning text and play the hint audio.
        hintMessage.classList.remove('hidden');
        hintAudio.src = event.hintAudioUrl;
        hintAudio.play();
    }
}