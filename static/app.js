const chatBox = document.getElementById('chat-box');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const micBtn = document.getElementById('mic-btn');
const status = document.getElementById('status');

let sessionId = crypto.randomUUID();
let recognition = null;

// --- Web Speech API: Speech-to-Text ---
if ('webkitSpeechRecognition' in window) {
    recognition = new webkitSpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        userInput.value = transcript;
        status.textContent = '';
        sendMessage(transcript);
    };

    recognition.onstart = () => {
        status.textContent = 'Listening...';
        micBtn.classList.add('active');
    };

    recognition.onend = () => {
        micBtn.classList.remove('active');
    };

    recognition.onerror = (event) => {
        status.textContent = 'Mic error: ' + event.error;
        micBtn.classList.remove('active');
    };
} else {
    micBtn.disabled = true;
    micBtn.title = 'Speech recognition not supported';
}

micBtn.addEventListener('click', () => {
    if (recognition) recognition.start();
});

sendBtn.addEventListener('click', () => {
    const msg = userInput.value.trim();
    if (msg) sendMessage(msg);
});

userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        const msg = userInput.value.trim();
        if (msg) sendMessage(msg);
    }
});

// --- Send message to backend ---
async function sendMessage(text) {
    addMessage('user', text);
    userInput.value = '';
    status.textContent = 'Thinking...';

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: text,
                session_id: sessionId
            })
        });
        const data = await res.json();

        const cleanText = data.response.replace(/```json\s*({[^}]+})\s*```/, '').trim();
        addMessage('assistant', cleanText);
        //addMessage('assistant', data.response);
        status.textContent = '';

        // Step 10: Detect JSON and trigger booking
        const jsonMatch = data.response.match(/```json\s*({[^}]+})\s*```/);
        if (jsonMatch) {
            try {
                const booking = JSON.parse(jsonMatch[1]);
                if (booking.action === 'book_appointment') {
                    await bookAppointment(booking);
                }
            } catch (e) { console.error('Parse error', e); }
        }

        // Play Cloud TTS audio
        if (data.audio) playAudio(data.audio);
    } catch (err) {
        status.textContent = 'Error: ' + err.message;
    }
}

// Step 10: Booking helper function (placed outside sendMessage)
async function bookAppointment(data) {
    const res = await fetch('/api/book', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    const result = await res.json();
    if (result.success) {
        addMessage('system', 'Appointment booked! Check your email for the calendar invite.');
    }
}

// --- Play base64 MP3 audio (from Cloud TTS) ---
function playAudio(base64Audio) {
    const audio = new Audio(
        'data:audio/mp3;base64,' + base64Audio
    );
    audio.play();
}

// --- Add message to chat UI ---
function addMessage(role, text) {
    const div = document.createElement('div');
    div.className = 'message ' + role;
    div.textContent = text;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
}